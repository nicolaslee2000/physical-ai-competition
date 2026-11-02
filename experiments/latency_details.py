#!/usr/bin/env python3
"""Read-only latency audit of actual Positronic OTLP JSONL sidecars.

Example (on the task host, using its Python with pyarrow for .zst traces):
  python experiments/latency_details.py --expected-episodes 20 \
    --policy-run baseline=experiments/results/BATCH/baseline \
    --policy-run horizon6=experiments/results/BATCH/horizon6

Outputs JSON to stdout; exits 2 if any policy's trace is missing/incomplete.
Warmup means the first N chronological calls of the whole policy run (default 1),
not measured compiler activity. First call per episode is also reported. All
latencies are client-observed policy.infer round trips, not pure model time.
No score or official runtime guarantee is inferred. The 15s flag applies only
to observed closed calls; open/unflushed calls cannot be recovered from traces.
"""
import argparse
import io
import json
import math
from pathlib import Path


def attributes(rows):
    result = {}
    for row in rows:
        value = row['value']
        for kind in ('stringValue', 'intValue', 'doubleValue', 'boolValue'):
            if kind in value:
                result[row['key']] = int(value[kind]) if kind == 'intValue' else value[kind]
                break
    return result


def read_harness(telemetry):
    spans, issues = {}, []
    files = sorted(telemetry.glob('*.spans.jsonl*')) if telemetry.is_dir() else []
    if not files:
        issues.append('No span sidecars found')
    for path in files:
        try:
            if path.name.endswith('.zst'):
                import pyarrow as pa  # Same zstd reader used by upstream telemetry.py.
                stream = io.TextIOWrapper(pa.input_stream(str(path), compression='zstd'))
            else:
                stream = path.open()
            with stream:
                for number, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        doc = json.loads(line)
                        if not doc.get('resourceSpans'):
                            raise ValueError('Missing resourceSpans')
                        for resource in doc['resourceSpans']:
                            identity = attributes(resource.get('resource', {}).get('attributes', []))
                            if identity.get('process.name') != 'harness':
                                continue
                            for scope in resource.get('scopeSpans', []):
                                for raw in scope.get('spans', []):
                                    start, end = int(raw['startTimeUnixNano']), int(raw['endTimeUnixNano'])
                                    if end < start or start <= 0:
                                        raise ValueError('Invalid timestamps')
                                    key = (identity.get('run.id', ''), raw['traceId'], raw['spanId'])
                                    if key in spans:
                                        raise ValueError('Duplicate span identity')
                                    spans[key] = dict(name=raw['name'], start=start, end=end,
                                                      parent=(key[0], key[1], raw.get('parentSpanId', '')),
                                                      attrs=attributes(raw.get('attributes', [])),
                                                      error=raw.get('status', {}).get('code') in (2, 'STATUS_CODE_ERROR'))
                    except (ValueError, KeyError, TypeError, AttributeError) as exc:
                        issues.append(f'{path.name}:{number}: malformed/incomplete OTLP line ({type(exc).__name__})')
        except (ImportError, OSError, ValueError) as exc:
            issues.append(f'{path.name}: unreadable trace ({type(exc).__name__}; .zst requires pyarrow)')
    return spans, issues


def distribution(values):
    ordered = sorted(values)
    def percentile(q):
        if not ordered:
            return None
        position = (len(ordered) - 1) * q
        low, high = math.floor(position), math.ceil(position)
        return ordered[low] + (ordered[high] - ordered[low]) * (position - low)
    return {'calls': len(values), 'p50_ms': percentile(.5), 'p95_ms': percentile(.95),
            'max_ms': max(values) if values else None}


def report(run_dir, expected_episodes, warmup_calls=1):
    spans, issues = read_harness(run_dir / 'episodes/telemetry')
    passes = [key for key, span in spans.items() if span['name'] == 'eval.pass']
    episodes = {key: span for key, span in spans.items() if span['name'] == 'episode'}
    if len(passes) != 1:
        issues.append(f'Expected one closed eval.pass span, found {len(passes)}')
    if len(episodes) != expected_episodes:
        issues.append(f'Expected {expected_episodes} closed episodes, found {len(episodes)}')
    if any(span['attrs'].get('pass.failed') for span in spans.values() if span['name'] == 'eval.pass'):
        issues.append('Pass marked failed')
    if any(span['attrs'].get('episode.partial') for span in episodes.values()):
        issues.append('Partial episode span')
    indices = [span['attrs'].get('episode.index') for span in episodes.values()]
    if None in indices or len(set(indices)) != len(indices):
        issues.append('Missing or duplicate episode.index')
    for episode in episodes.values():
        if episode['parent'] not in passes:
            issues.append('Episode not parented by the sole pass')
    calls = []
    for key, span in spans.items():
        if span['name'] != 'policy.infer':
            continue
        parent, visited = span['parent'], {key}
        while parent in spans and parent not in episodes and parent not in visited:
            visited.add(parent)
            parent = spans[parent]['parent']
        if parent not in episodes:
            issues.append('Inference has no recorded ancestor episode')
            continue
        if span['error']:
            issues.append('Inference span marked error')
        calls.append({'start_unix_ns': span['start'], 'duration_ms': (span['end'] - span['start']) / 1e6,
                      'episode_index': episodes[parent]['attrs'].get('episode.index'),
                      'molmo_episode_index': episodes[parent]['attrs'].get('molmo.episode_index'),
                      'episode_span_id': parent[2], 'span_id': key[2]})
    calls.sort(key=lambda row: (row['start_unix_ns'], row['span_id']))
    per_episode = []
    for key, episode in sorted(episodes.items(), key=lambda pair: pair[1]['start']):
        rows = [row for row in calls if row['episode_span_id'] == key[2]]
        if not rows:
            issues.append(f'Episode {episode["attrs"].get("episode.index")} has no inference calls')
        per_episode.append({'episode_index': episode['attrs'].get('episode.index'),
                            'molmo_episode_index': episode['attrs'].get('molmo.episode_index'), 'episode_span_id': key[2],
                            'wall_ms': (episode['end'] - episode['start']) / 1e6,
                            'first_inference': rows[0] if rows else None,
                            **distribution([row['duration_ms'] for row in rows])})
    if not calls:
        issues.append('No inference spans')
    issues = list(dict.fromkeys(issues))
    maximum = max(calls, key=lambda row: row['duration_ms']) if calls else None
    return {'trace_complete': not issues, 'issues': issues, 'closed_episodes': len(episodes),
            'expected_episodes': expected_episodes, 'first_inference': calls[0] if calls else None,
            'warmup_definition': f'first {warmup_calls} chronological run calls; operational exclusion, not measured compilation',
            'observed_all': distribution([row['duration_ms'] for row in calls]),
            'observed_warmup': distribution([row['duration_ms'] for row in calls[:warmup_calls]]),
            'observed_steady': distribution([row['duration_ms'] for row in calls[warmup_calls:]]),
            'worst_inference': maximum,
            'worst_episode_by_max_inference': max(per_episode, key=lambda row: row['max_ms'] if row['max_ms'] is not None else -1) if per_episode else None,
            'observed_all_calls_within_15s': maximum['duration_ms'] <= 15000 if maximum and not issues else None,
            'episodes': per_episode,
            'scope': 'client policy.infer round trip, including server/protocol wait; image preparation excluded; no official-runtime guarantee',
            'completeness_limit': 'closed-span audit only; a silently lost inference span cannot be proven absent without an independent call counter'}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--policy-run', action='append', required=True, metavar='NAME=PATH')
    parser.add_argument('--expected-episodes', type=int, required=True)
    parser.add_argument('--warmup-calls', type=int, default=1)
    args = parser.parse_args()
    if args.expected_episodes <= 0 or args.warmup_calls < 0:
        parser.error('Expected episodes must be positive; warmup calls must be nonnegative')
    results = {}
    for entry in args.policy_run:
        name, separator, path = entry.partition('=')
        if not name or not separator or not path or name in results:
            parser.error('Provide unique NAME=PATH entries')
        results[name] = report(Path(path), args.expected_episodes, args.warmup_calls)
    print(json.dumps(results, indent=2, allow_nan=False))
    return 0 if all(result['trace_complete'] for result in results.values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
