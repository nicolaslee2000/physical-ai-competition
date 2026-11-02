#!/usr/bin/env python3
"""Read-only comparison of two completed public mini practice runs; JSON stdout.

Example: python compare_recordings.py --control-run ROOT/experiments/results/BATCH/baseline
  --candidate-run ROOT/experiments/results/BATCH/horizon-6of15

Both policy directories must have result.json status=complete before ANY episode
is read. Computes no selection or promotion decision. Requires the installed
Positronic/positronic_evals versions matching the recordings.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path


def require_completed(paths):
    statuses = [json.loads((path / 'result.json').read_text()) for path in paths]
    if any(status.get('status') != 'complete' for status in statuses):
        raise ValueError('Both policy runs must be complete before reading any recordings')
    return statuses


def wilson(successes, total):
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError('Invalid binomial sample counts')
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    half = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return [max(0, centre - half), min(1, centre + half)]


def mcnemar_exact(improved, regressed):
    if min(improved, regressed) < 0:
        raise ValueError('Discordance counts must be nonnegative')
    discordant = improved + regressed
    if not discordant:
        return 1.0
    return min(1.0, 2 * sum(math.comb(discordant, k) for k in range(min(improved, regressed) + 1)) / 2 ** discordant)


def validate_rows(rows, expected):
    indices = [row['index'] for row in rows]
    if Counter(indices) != Counter(expected):
        raise ValueError('Episode coverage differs from the exact upstream public mini definition')
    if any(row['score'] not in (0, 1) or not math.isfinite(row['score']) for row in rows):
        raise ValueError('Unscored/nonbinary episode outcome')
    return {row['index']: row for row in rows}


def compare_split(control, candidate, indices):
    outcomes = Counter()
    rows = []
    missing = {'task_instruction': [], 'camera_slot_sides': []}
    for index in sorted(indices):
        left, right = control[index], candidate[index]
        checks = {}
        for key in missing:
            if left.get(key) is None or right.get(key) is None:
                missing[key].append(index)
                checks[key] = 'missing'
            elif left[key] != right[key]:
                raise ValueError(f'Episode {index}: mismatched {key}; cannot treat as matched observations')
            else:
                checks[key] = 'matched'
        pair = (left['score'], right['score'])
        outcome = {(0, 0): 'both_fail', (1, 1): 'both_success', (0, 1): 'improved', (1, 0): 'regressed'}[pair]
        outcomes[outcome] += 1
        rows.append({'index': index, 'control': int(pair[0]), 'candidate': int(pair[1]), 'comparison': outcome,
                     'metadata_checks': checks, 'control_label_outcome': left.get('label_outcome'),
                     'candidate_label_outcome': right.get('label_outcome')})
    n = len(rows)
    counts = {name: outcomes[name] for name in ('both_success', 'both_fail', 'improved', 'regressed')}
    control_successes = counts['both_success'] + counts['regressed']
    candidate_successes = counts['both_success'] + counts['improved']
    return {'episodes': n, 'control': {'successes': control_successes, 'rate': control_successes / n, 'wilson_95': wilson(control_successes, n)},
            'candidate': {'successes': candidate_successes, 'rate': candidate_successes / n, 'wilson_95': wilson(candidate_successes, n)},
            **counts, 'paired_net_successes': counts['improved'] - counts['regressed'],
            'paired_rate_difference': (counts['improved'] - counts['regressed']) / n,
            'mcnemar_exact_two_sided_p': mcnemar_exact(counts['improved'], counts['regressed']),
            'missing_metadata_indices': missing, 'per_episode': rows}


def read_rows(path, definition):
    from positronic import keys
    from positronic.dataset.local_dataset import LocalDataset
    from positronic.dataset.episode import META_PATH
    from positronic_evals.labels import label, Outcome
    from positronic_evals.scoring import episode_score
    metric = definition.scoring.primary
    rows = []
    for episode in LocalDataset(path / 'episodes'):
        given = label(Path(episode.meta[META_PATH]), definition.scoring.labelers)
        if given is None or given[1].outcome is Outcome.INVALID:
            raise ValueError('Episode has no valid upstream outcome label')
        observed = given[1]
        rows.append({'index': episode.static.get('molmo.episode_index'),
                     'score': episode_score(observed, metric.episode_score, metric.time_limit_s),
                     'label_outcome': observed.outcome.name,
                     'task_instruction': episode.static.get(keys.TASK),
                     'camera_slot_sides': episode.static.get('molmo.exterior_sides')})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--control-run', type=Path, required=True)
    parser.add_argument('--candidate-run', type=Path, required=True)
    args = parser.parse_args()
    paths = [args.control_run, args.candidate_run]
    root = Path('/opt/hderc-internal/nick/physical-ai-competition')
    if any(not path.resolve().is_relative_to(root) for path in paths) or paths[0].resolve() == paths[1].resolve():
        parser.error('Provide two distinct policy run paths within the isolated task root')
    statuses = require_completed(paths)  # Gate BOTH before even loading a dataset.
    from positronic_evals.evals import EvalRef, public_eval, MOLMO_EPISODE_INDEX_KEY
    definition = public_eval(EvalRef('molmo.franka_pick_mini'))
    smoke = public_eval(EvalRef('molmo.franka_pick_mini_smoke'))
    expected = [trial[MOLMO_EPISODE_INDEX_KEY] for task in definition.tasks for trial in task.trials]
    development = {trial[MOLMO_EPISODE_INDEX_KEY] for task in smoke.tasks for trial in task.trials}
    if len(expected) != 20 or len(set(expected)) != 20 or len(development) != 5 or not development.issubset(expected):
        raise ValueError('Upstream suite changed; review the fixed development/validation split')
    control, candidate = [validate_rows(read_rows(path, definition), expected) for path in paths]
    result = {'control_run': str(paths[0]), 'candidate_run': str(paths[1]),
              'control_image': statuses[0].get('image'), 'candidate_image': statuses[1].get('image'),
              'development': compare_split(control, candidate, development),
              'validation': compare_split(control, candidate, set(expected) - development),
              'pairing': 'matched public episode indices; available task instructions and exterior-slot sides checked; matching random seeds and all simulator stochasticity are not established',
              'caveat': 'Local public practice only, not competition private evaluation. One trial per episode; small samples yield wide Wilson intervals. Exact McNemar conditions on discordant pairs and assumes valid independent pairs. No automatic selection or promotion; repeated validation inspection changes its role.'}
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
