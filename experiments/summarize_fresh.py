#!/usr/bin/env python3
"""Read-only JSON summary of a frozen fresh local public pick/placement cohort; not an official score."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path



PICK_BENCHMARK = 'molmospaces-bench-v2/procthor-10k/FrankaPickDroidMiniBench/FrankaPickDroidMiniBench_json_benchmark_20251231'
PLACEMENT_BENCHMARK = 'molmospaces-bench-v2/procthor-objaverse/FrankaPickandPlaceNextToHardBench/FrankaPickandPlaceNextToHardBench_20260305_json_benchmark'


def cohort_description(cohort):
    benchmark = cohort['benchmark']
    if benchmark == PICK_BENCHMARK:
        return {'expected_episodes': 20, 'scope': 'fresh local public pick-only validation; not official competition score',
                'visibility_caveat': 'Curated right-view blocked episodes excluded; remaining views are not guaranteed unobstructed.'}
    if benchmark == PLACEMENT_BENCHMARK:
        return {'expected_episodes': 10, 'scope': 'fresh local public next-to placement diagnostic; not official competition score',
                'visibility_caveat': 'No curated right-view blocklist entry exists for this benchmark. Right-view visibility is unknown; do not post-select by visibility or outcome.'}
    raise ValueError('Unsupported benchmark: only exact frozen Mini and NextToHard families are supported')


def frozen_cohort(path, digest, blocked):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Frozen cohort SHA256 mismatch')
    cohort = json.loads(raw)
    rows = cohort['episodes']
    benchmark = cohort['benchmark']
    description = cohort_description(cohort)
    count = description['expected_episodes']
    if not cohort['status'].startswith('frozen_') or len(rows) != count or cohort['manifest']['episode_count'] != 1000:
        raise ValueError('Frozen cohort count or manifest size differs from the restricted benchmark specification')
    indices = [row['episode_index'] for row in rows]
    if len(set(indices)) != count or any(type(index) is not int or not 21 <= index < 1000 for index in indices):
        raise ValueError('Duplicate, previous, or out-of-range episode index')
    if benchmark == PICK_BENCHMARK:
        if benchmark not in blocked or set(indices) & set(blocked[benchmark]):
            raise ValueError('Missing Mini blocklist or blocked episode selected')
    elif cohort['selection'].get('right_view_blocklist_key_present') is not False or benchmark in blocked:
        raise ValueError('NextToHard requires explicit frozen absent-blocklist provenance; visibility remains unknown')
    if Counter(row['eval_seed'] for row in rows) != {0: count // 2, 1: count // 2}:
        raise ValueError('Expected two equally sized seed cohorts')
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
    description = cohort_description(cohort)
    expected_count = description['expected_episodes']
    per_seed = Counter(row['eval_seed'] for row in cohort['episodes'])
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
        timings[str(seed)] = checked_latency(json.loads((root / 'episodes/timing_summary.json').read_text()), per_seed[seed])
    expected = {row['episode_index']: row for row in cohort['episodes']}
    validate_coverage(rows, expected)
    scores = score(MOLMO_SCORING, labels)
    if scores.unscored or scores.episodes != expected_count:
        raise ValueError('Incomplete scores')
    return {**description, 'task_family': cohort['task_family'], 'benchmark': cohort['benchmark'],
            'trial_caveat': 'Single trial per episode; no automatic selection or promotion.',
            'manifest_sha256': cohort['manifest']['sha256'],
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
