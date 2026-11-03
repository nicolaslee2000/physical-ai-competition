#!/usr/bin/env python3
"""Synthetic prompt-shape qualification; dry-run unless --execute, no simulator/rendering.

Use an explicit two-image plan and recorded DEVELOPMENT dataset. Container address,
namespace, guard, lock, timeouts, resource monitor and cleanup come from qualify_images.
--client is the internal namespace client mode, not a separate public endpoint guess.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import qualify_images as images
import qualify_sessions as sessions

LENGTHS = (4, 128, 8, 96, 16, 120, 6, 80, 12, 112, 14, 124)
VRAM_BUDGET_BYTES = 22_000_000_000


def synthetic_prompt(index):
    if not 0 <= index < len(LENGTHS):
        raise ValueError('Unknown synthetic prompt index')
    words = 'pick the blue object and place it beside the small green box on the clean table with care using a steady gentle motion'.split()
    words[2] = ('blue', 'red', 'yellow', 'green', 'white', 'black', 'orange', 'purple', 'silver', 'brown', 'pink', 'gray')[index]
    return ' '.join(words[position % len(words)] for position in range(LENGTHS[index]))


def prompt_metadata(index):
    text = synthetic_prompt(index)
    return {'index': index, 'words': len(text.split()), 'characters': len(text), 'sha256': hashlib.sha256(text.encode()).hexdigest()}


def memory_report(path):
    samples, malformed = [], 0
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
                gpu = row['gpu_card']
                if gpu.get('returncode') != 0:
                    continue
                fields = [value.strip() for value in gpu['sample'].split(',')]
                if fields[0] != images.h.GPU:
                    continue
                mib = float(fields[1])
                if not math.isfinite(mib) or mib < 0:
                    raise ValueError('Invalid sample')
                samples.append(mib * 1024 * 1024)
            except (ValueError, KeyError, IndexError, TypeError):
                malformed += 1
    maximum = max(samples) if samples else None
    exceeded = maximum is not None and maximum >= VRAM_BUDGET_BYTES
    return {'budget_bytes': VRAM_BUDGET_BYTES, 'samples': len(samples), 'malformed_samples': malformed,
            'max_sampled_card_bytes': maximum,
            'sampled_headroom_bytes': VRAM_BUDGET_BYTES - maximum if maximum is not None else None,
            'passed': False if exceeded else None,
            'status': 'failed_observed_card_total_at_or_above_budget' if exceeded else 'unknown_true_peak_not_instrumented',
            'scope': 'entire assigned GPU card, not process attribution; sparse samples can miss transient old/new graph-pool overlap; no VRAM cap or peak compliance claimed'}


def checked_prompt_report(path, indices):
    indices = [indices] if isinstance(indices, int) else indices
    result = images.checked_report(path, len(indices))
    if not sessions.aggregate(result.get('workers', []), len(indices))['passed']:
        raise ValueError('Worker lifecycle/latency evidence failed revalidation')
    if result.get('prompts') != [prompt_metadata(index) for index in indices]:
        raise ValueError('Prompt coverage/hash differs from requested synthetic case')
    workers = result['workers']
    if len(workers) != len(indices) or {worker['worker'] for worker in workers} != set(range(len(indices))):
        raise ValueError('Missing or duplicated prompt workers')
    waves = [wave for worker in workers for wave in worker['waves']]
    if len(waves) != 2 * len(indices) or any(len(wave['infer_ms']) < 2 or wave.get('validated_inference_results', 0) < 2 for wave in waves):
        raise ValueError('Each fresh session must include recapture/steady calls')
    return result


def run_sweep(plan, address, image, directory, env, guard):
    rows, concurrent = [], None
    started = time.time()
    try:
        for index in range(10):
            guard(directory / f'prompt-{index}-guard.log')
            output = directory / f'prompt-{index}.json'
            command = images.h.namespace_command([
                plan['python'], str(images.h.ROOT / 'experiments/qualify_prompts.py'), '--client',
                '--prompt-index', str(index), '--url', f'ws://{address}:8000', '--image', image,
                '--recordings', plan['recordings']])
            images.h.bounded(command, output, env, 180, Path(plan['repo']))
            report = checked_prompt_report(output, index)
            rows.append({'prompt': prompt_metadata(index), 'report_path': str(output), 'calls': report['calls'],
                         'p50_ms': report['p50_ms'], 'p95_ms': report['p95_ms'], 'max_ms': report['max_ms'],
                         'fresh_sessions': [{'first_infer_ms': wave['infer_ms'][0], 'following_infer_ms': wave['infer_ms'][1:]} for wave in report['workers'][0]['waves']]})
        guard(directory / 'concurrent-guard.log')
        output = directory / 'concurrent-12.json'
        command = images.h.namespace_command([plan['python'], str(images.h.ROOT / 'experiments/qualify_prompts.py'), '--client', '--concurrent', '--url', f'ws://{address}:8000', '--image', image, '--recordings', plan['recordings']])
        images.h.bounded(command, output, env, 180, Path(plan['repo']))
        concurrent = checked_prompt_report(output, list(range(12)))
    finally:
        summary = {'functional_passed': len(rows) == 10 and concurrent is not None, 'prompts': rows, 'concurrent_12': concurrent,
                   'started_unix': started, 'finished_unix': time.time(),
                   'memory_gate': memory_report(directory / 'resources.jsonl'),
                   'ready_for_fresh_validation': False,
                   'scope': 'synthetic prompt-shape/lifecycle/latency qualification only; no task-success or untouched validation text used'}
        (directory / 'prompt-sweep-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    if summary['memory_gate']['passed'] is False:
        raise ValueError('Observed GPU card total reached the 22GB card-total threshold (2GB below24GB)')
    # Functional success may coexist with UNKNOWN peak-memory compliance; never silently promote it.
    return {'prompt_sweep': summary, 'qualification_passed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--recordings', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--client', action='store_true')
    parser.add_argument('--concurrent', action='store_true')
    parser.add_argument('--url')
    parser.add_argument('--image')
    parser.add_argument('--prompt-index', type=int)
    args = parser.parse_args()
    images.h.owned(args.recordings)
    if args.client:
        if args.execute or (args.prompt_index is None and not args.concurrent) or (args.prompt_index is not None and args.concurrent):
            parser.error('Internal client requires an explicit prompt index')
        host, port = sessions.validate_identity(args.url, args.image)
        indices = list(range(12)) if args.concurrent else [args.prompt_index]
        overrides = [synthetic_prompt(index) for index in indices]
        result = sessions.qualify(host, port, args.recordings, len(indices), 2, task_override=overrides)
        result.update(prompts=[prompt_metadata(index) for index in indices], image=args.image)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result['passed'] else 2
    if args.plan is None:
        parser.error('Explicit pinned stock/graph plan required')
    plan = images.validated_plan(json.loads(args.plan.read_text()), args.recordings)
    plan.update(qualification='synthetic-prompt-shape', stages=['serial-10', 'mixed-12'], prompts=[prompt_metadata(index) for index in range(len(LENGTHS))],
                vram_card_threshold_bytes=VRAM_BUDGET_BYTES, concurrent_sessions=12,
                worst_case_seconds=2 * (plan['ready_timeout_s'] + 11 * 180 + 360) + 90)
    print(json.dumps(plan, indent=2), flush=True)
    if args.execute:
        results = images.execute(plan, stage_runner=run_sweep)
        print(json.dumps({'results': str(results)}))
        return 0 if all(row['status'] == 'passed' for row in json.loads(results.read_text())) else 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
