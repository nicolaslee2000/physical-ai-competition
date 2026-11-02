#!/usr/bin/env python3
"""Validate upstream records and score the predeclared smoke/holdout split."""
import argparse
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('upstream_local_eval', args.repo / 'integration_tests/molmo_local_eval.py')
    upstream = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(upstream)
    from positronic_evals.evals import EvalRef, public_eval, MOLMO_EPISODE_INDEX_KEY
    from positronic_evals.labels import label
    from positronic_evals.scoring import score
    from positronic.dataset.local_dataset import LocalDataset
    from positronic.dataset.episode import META_PATH

    definition = public_eval(EvalRef('molmo.franka_pick_mini'))
    # Checks exact episode multiplicity, labelability and the printed score.
    full = upstream.recorded_score(definition, args.run_dir / 'episodes')
    upstream.check_log(args.run_dir / 'eval.log', full)
    smoke_indices = {0, 1, 2, 3, 4}
    holdout_indices = {5, *range(7, 21)}
    groups = {'smoke': [], 'holdout': []}
    for episode in LocalDataset(args.run_dir / 'episodes'):
        index = episode.static[MOLMO_EPISODE_INDEX_KEY]
        if index not in smoke_indices | holdout_indices:
            raise ValueError(f'Unexpected practice episode {index}; review the fixed split')
        labelled = label(Path(episode.meta[META_PATH]), definition.scoring.labelers)
        if labelled is None:
            raise ValueError(f'Unlabelled episode {index}')
        groups['smoke' if index in smoke_indices else 'holdout'].append(labelled[1])
    if len(groups['smoke']) != 5 or len(groups['holdout']) != 15:
        raise ValueError('Upstream practice suite changed; review the fixed split')
    result = {'full': full.model_dump(), **{name: score(definition.scoring, rows).model_dump() for name, rows in groups.items()},
              'holdout_episode_indices': sorted(holdout_indices)}
    timing = json.loads((args.run_dir / 'episodes/timing_summary.json').read_text())
    if timing['episodes'] != 20 or timing['window'] != 'W_pass' or timing['infer_calls'] <= 0:
        raise ValueError('Incomplete or missing timing; cannot compare latency')
    result['latency'] = {key: timing[key] for key in ('infer_calls', 'infer_p50_ms', 'infer_p95_ms', 'wall_s', 'window')}
    result['latency_scope'] = 'all 20 practice episodes; client-observed inference round trip'
    (args.run_dir / 'metrics.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
