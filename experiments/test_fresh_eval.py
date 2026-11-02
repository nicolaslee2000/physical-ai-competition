"""Offline frozen-plan/coverage checks; no server, simulator, or scores read."""
import ast
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fresh_eval as fresh
import summarize_fresh as summary

HERE = Path(__file__).parent
BLOCKLIST = HERE.parents[1] / 'positronic/evals/positronic_evals/right_view_blocked.json'
COHORT = HERE / 'fresh-pick-cohort.json'


class FreshTests(unittest.TestCase):
    def frozen(self):
        raw = COHORT.read_bytes()
        return summary.frozen_cohort(COHORT, hashlib.sha256(raw).hexdigest(), json.loads(BLOCKLIST.read_text()))

    def test_frozen_actual_cohort_and_hash_tamper(self):
        self.assertEqual(len(self.frozen()['episodes']), 20)
        with self.assertRaises(ValueError):
            summary.frozen_cohort(COHORT, '0' * 64, json.loads(BLOCKLIST.read_text()))

    def test_overlap_duplicate_out_of_range_and_blocked_rejected(self):
        original = self.frozen()
        for index in (0, 1000, original['episodes'][1]['episode_index']):
            cohort = copy.deepcopy(original)
            cohort['episodes'][0]['episode_index'] = index
            with tempfile.TemporaryDirectory(dir=HERE) as directory:
                path = Path(directory) / 'cohort.json'
                raw = json.dumps(cohort).encode()
                path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    summary.frozen_cohort(path, hashlib.sha256(raw).hexdigest(), json.loads(BLOCKLIST.read_text()))
        blocked = {original['benchmark']: [original['episodes'][0]['episode_index']]}
        with self.assertRaises(ValueError):
            summary.frozen_cohort(COHORT, hashlib.sha256(COHORT.read_bytes()).hexdigest(), blocked)

    def test_exact_coverage_seed_camera_and_path(self):
        cohort = self.frozen()
        expected = {value['episode_index']: value for value in cohort['episodes']}
        rows = [{'index': index, 'path': value['episode_path'], 'seed': value['eval_seed'], 'camera_order': value['camera_order'], 'score': 1} for index, value in expected.items()]
        summary.validate_coverage(rows, expected)
        for name, value in (('seed', 9), ('camera_order', None), ('path', 'incorrect'), ('score', .5)):
            changed = copy.deepcopy(rows)
            changed[0][name] = value
            with self.assertRaises(ValueError):
                summary.validate_coverage(changed, expected)
        with self.assertRaises(ValueError):
            summary.validate_coverage(rows[:-1], expected)

    def test_cli_is_supported_custom_eval_not_platform(self):
        rows = [value for value in self.frozen()['episodes'] if value['eval_seed'] == 0]
        command = fresh.eval_command('positronic', '172.25.0.2', rows, '/owned/output')
        self.assertIn('--eval=.sim.molmo.benchmarks', command)
        self.assertIn('--eval.seed=0', command)
        self.assertIn('--eval.trial_count=1', command)
        paths = ast.literal_eval(next(value.split('=', 1)[1] for value in command if value.startswith('--eval.episode_paths=')))
        self.assertEqual(paths, [value['episode_path'] for value in rows])
        self.assertFalse(any('policy-image' in value for value in command))

    def test_dry_run_does_not_spawn(self):
        args = ['fresh_eval.py', '--plan', str(HERE / 'plan-horizon-validation.json'), '--cohort', str(COHORT), '--cohort-sha256', hashlib.sha256(COHORT.read_bytes()).hexdigest(), '--blocklist', str(BLOCKLIST)]
        with patch('sys.argv', args), patch('subprocess.run') as run, patch.object(fresh.h, 'bounded') as bounded, contextlib.redirect_stdout(io.StringIO()) as output:
            fresh.main()
        self.assertIn('cohort_sha256', json.loads(output.getvalue()))
        run.assert_not_called()
        bounded.assert_not_called()


if __name__ == '__main__':
    unittest.main()
