"""Offline exact-count/statistical/matching checks; no recorded results are read."""
import json
from pathlib import Path
import tempfile
import unittest

import compare_recordings as compare

HERE = Path(__file__).parent


def rows(values):
    return {i: {'index': i, 'score': value, 'task_instruction': 'pick object', 'camera_slot_sides': ['left', 'right']} for i, value in enumerate(values)}


class ComparisonTests(unittest.TestCase):
    def test_exact_mcnemar_discordant_pairs_and_no_discordance(self):
        self.assertEqual(compare.mcnemar_exact(0, 0), 1)
        self.assertEqual(compare.mcnemar_exact(5, 0), .0625)
        self.assertEqual(compare.mcnemar_exact(0, 5), .0625)
        self.assertEqual(compare.mcnemar_exact(2, 2), 1)

    def test_wilson_known_boundary_and_small_sample(self):
        low, high = compare.wilson(0, 5)
        self.assertAlmostEqual(low, 0)
        self.assertAlmostEqual(high, .43448246478317476)
        self.assertAlmostEqual(compare.wilson(5, 5)[0], 1 - high)

    def test_per_index_pair_counts_and_net_rate(self):
        result = compare.compare_split(rows([1, 0, 1, 0, 0]), rows([1, 1, 0, 0, 1]), set(range(5)))
        self.assertEqual([result[name] for name in ('both_success', 'both_fail', 'improved', 'regressed')], [1, 1, 2, 1])
        self.assertEqual(result['paired_net_successes'], 1)
        self.assertEqual(result['paired_rate_difference'], .2)
        self.assertEqual(result['control']['successes'], 2)
        self.assertEqual(result['candidate']['successes'], 3)

    def test_duplicate_unscored_nonbinary_coverage_rejected(self):
        for values in ([{'index': 0, 'score': 1}, {'index': 0, 'score': 0}],
                       [{'index': 0, 'score': .5}, {'index': 1, 'score': 0}],
                       [{'index': 0, 'score': None}, {'index': 1, 'score': 0}]):
            with self.assertRaises(ValueError):
                compare.validate_rows(values, [0, 1])

    def test_metadata_mismatch_refused_missing_explicit(self):
        control, candidate = rows([1]), rows([1])
        candidate[0]['camera_slot_sides'] = ['right', 'left']
        with self.assertRaises(ValueError):
            compare.compare_split(control, candidate, {0})
        candidate[0]['camera_slot_sides'] = None
        result = compare.compare_split(control, candidate, {0})
        self.assertEqual(result['missing_metadata_indices']['camera_slot_sides'], [0])

    def test_both_completion_markers_required(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            paths = [Path(directory) / name for name in ('control', 'candidate')]
            for path, status in zip(paths, ('complete', 'failed')):
                path.mkdir()
                (path / 'result.json').write_text(json.dumps({'status': status}))
            with self.assertRaises(ValueError):
                compare.require_completed(paths)
            (paths[1] / 'result.json').write_text('{"status":"complete"}')
            self.assertEqual(len(compare.require_completed(paths)), 2)


if __name__ == '__main__':
    unittest.main()
