#!/usr/bin/env python3
"""Read-only JSON summary of a frozen fresh local public pick cohort; not an official score."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def frozen_cohort(path, digest, blocked):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Frozen cohort SHA256 mismatch')
    cohort = json.loads(raw)
    rows = cohort['episodes']
    benchmark = cohort['benchmark']
    if not cohort['status'].startswith('frozen_') or len(rows) != 20 or cohort['manifest']['episode_count'] != 1000:
        raise ValueError('Expected frozen 20-episode/1000-entry mini cohort')
    indices = [row['episode_index'] for row in rows]
    if len(set(indices)) != 20 or any(type(index) is not int or not 21 <= index < 1000 for index in indices):
        raise ValueError('Duplicate, previous, or out-of-range episode index')
    if benchmark not in blocked or set(indices) & set(blocked[benchmark]):
        raise ValueError('Missing benchmark blocklist or blocked episode selected')
    if Counter(row['eval_seed'] for row in rows) != {0: 10, 1: 10}:
        raise ValueError('Expected two ten-episode seed cohorts')
    for row in rows:
        if row['episode_path'] != f'{benchmark}/{row["episode_index"]}' or row['camera_order'] != (['right', 'left'] if row['eval_seed'] == 0 else ['left', 'right']):
            raise ValueError('Episode path or camera-order provenance differs')
    return cohort


def validate_coverage(rows, expected):
    if Counter(row['index'] for row in rows) != Counter(expected.keys()):
        raise ValueError('Recorded exact coverage differs from frozen cohort')
    for row in rows:
        target = expected[row['index']]
        if row['path'] != target['episode_path'] or row['seed'] != target['eval_seed'] or row['camera_order'] != target['camera_order']:
            raise ValueError('Recorded path/seed/camera order differs from frozen cohort')
        if row['score'] not in (0, 1):
            raise ValueError('Nonbinary outcome')


def summarize(run, cohort):
    from positronic.dataset.local_dataset import LocalDataset
    from positronic.dataset.episode import META_PATH
    from positronic_evals.evals import MOLMO_SCORING
    from positronic_evals.labels import label, Outcome
    from positronic_evals.scoring import score, episode_score
    from positronic.eval.keys import SEED
    from positronic.simulator.molmo_spaces.keys import BENCHMARK_DIMENSIONS
    from summarize_recordings import checked_latency
    rows, labels, timings = [], [], {}
    for seed in (0, 1):
        root = run / f'seed-{seed}'
        for episode in LocalDataset(root / 'episodes'):
            found = label(Path(episode.meta[META_PATH]), MOLMO_SCORING.labelers)
            if found is None or found[1].outcome is Outcome.INVALID:
                raise ValueError('Unscored or invalid episode')
            metric = MOLMO_SCORING.primary
            labels.append(found[1])
            static = episode.static
            index = static['molmo.episode_index']
            rows.append({'index': index, 'seed': static.get(SEED), 'camera_order': static.get('molmo.exterior_sides'),
                         'path': '/'.join(str(static[key]) for key in BENCHMARK_DIMENSIONS) + f'/{index}',
                         'recording_path': str(episode.meta[META_PATH]),
                         'score': episode_score(found[1], metric.episode_score, metric.time_limit_s)})
        timings[str(seed)] = checked_latency(json.loads((root / 'episodes/timing_summary.json').read_text()), 10)
    expected = {row['episode_index']: row for row in cohort['episodes']}
    validate_coverage(rows, expected)
    scores = score(MOLMO_SCORING, labels)
    if scores.unscored or scores.episodes != 20:
        raise ValueError('Incomplete scores')
    return {'scope': 'fresh local public pick-only validation, single trial per episode; not official competition score',
            'scores': scores.model_dump(), 'successes': sum(row['score'] for row in rows),
            'episodes': sorted(rows, key=lambda row: row['index']), 'cohort_timing': timings,
            'latency_note': 'per-cohort upstream client round trips; percentiles are not pooled across cohorts'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--cohort', type=Path, required=True)
    parser.add_argument('--cohort-sha256', required=True)
    parser.add_argument('--blocklist', type=Path, required=True)
    args = parser.parse_args()
    cohort = frozen_cohort(args.cohort, args.cohort_sha256, json.loads(args.blocklist.read_text()))
    result = summarize(args.run_dir, cohort)
    result['cohort_sha256'] = args.cohort_sha256
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
