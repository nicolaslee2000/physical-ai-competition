#!/usr/bin/env python3
"""Validate upstream records; development smoke or a separate practice holdout."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path

SMOKE = 'molmo.franka_pick_mini_smoke'
MINI = 'molmo.franka_pick_mini'


def split_coverage(definition, development_definition, episode_key):
    """Derive exact trial coverage and disjoint splits from upstream definitions."""
    expected = Counter(trial[episode_key] for task in definition.tasks for trial in task.trials)
    development = Counter(trial[episode_key] for task in development_definition.tasks for trial in task.trials)
    if not expected or any(count != 1 for count in expected.values()) or not development or any(count != 1 for count in development.values()):
        raise ValueError('Expected one trial per public episode; review upstream definitions')
    if development - expected:
        raise ValueError('Development episodes must belong to the selected public suite')
    return {'development': set(development), 'holdout': set(expected) - set(development)}


def checked_latency(timing, expected_count):
    if timing['episodes'] != expected_count or timing['window'] != 'W_pass' or timing['infer_calls'] <= 0:
        raise ValueError('Incomplete or missing timing; cannot compare latency')
    return {key: timing[key] for key in ('infer_calls', 'infer_p50_ms', 'infer_p95_ms', 'wall_s', 'window')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--eval', choices=(SMOKE, MINI), default=MINI)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('upstream_local_eval', args.repo / 'integration_tests/molmo_local_eval.py')
    upstream = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(upstream)
    from positronic_evals.evals import EvalRef, public_eval, MOLMO_EPISODE_INDEX_KEY
    from positronic_evals.labels import label
    from positronic_evals.scoring import score
    from positronic.dataset.local_dataset import LocalDataset
    from positronic.dataset.episode import META_PATH

    definition = public_eval(EvalRef(args.eval))
    development_definition = public_eval(EvalRef(SMOKE))
    splits = split_coverage(definition, development_definition, MOLMO_EPISODE_INDEX_KEY)
    # Verifies exact upstream episode multiplicity, labelability and printed score.
    full = upstream.recorded_score(definition, args.run_dir / 'episodes')
    upstream.check_log(args.run_dir / 'eval.log', full)
    groups = {name: [] for name, indices in splits.items() if indices}
    for episode in LocalDataset(args.run_dir / 'episodes'):
        index = episode.static[MOLMO_EPISODE_INDEX_KEY]
        group = next((name for name, indices in splits.items() if index in indices), None)
        if group is None:
            raise ValueError(f'Unexpected practice episode {index}')
        labelled = label(Path(episode.meta[META_PATH]), definition.scoring.labelers)
        if labelled is None:
            raise ValueError(f'Unlabelled episode {index}')
        groups[group].append(labelled[1])
    if any(len(groups.get(name, [])) != len(indices) for name, indices in splits.items()):
        raise ValueError('Recorded split coverage differs from upstream definitions')
    result = {'eval': args.eval, 'full': full.model_dump(),
              **{name: score(definition.scoring, rows).model_dump() for name, rows in groups.items()},
              'development_episode_indices': sorted(splits['development'])}
    if splits['holdout']:
        result['holdout_episode_indices'] = sorted(splits['holdout'])
    timing = json.loads((args.run_dir / 'episodes/timing_summary.json').read_text())
    count = sum(len(indices) for indices in splits.values())
    result['latency'] = checked_latency(timing, count)
    result['latency_scope'] = f'all {count} selected practice episodes; client-observed inference round trip'
    (args.run_dir / 'metrics.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
