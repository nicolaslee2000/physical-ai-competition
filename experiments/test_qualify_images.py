"""Offline wrapper checks; never invokes Docker, a model, or network namespace."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import qualify_images as wrapper

HERE = Path(__file__).parent


class WrapperTests(unittest.TestCase):
    def plan(self):
        return wrapper.validated_plan(json.loads((HERE / 'plan-horizon-validation.json').read_text()),
                                      wrapper.h.ROOT / 'experiments/results/smoke/baseline/episodes')

    def test_dry_run_has_no_external_calls(self):
        args = ['qualify_images.py', '--plan', str(HERE / 'plan-horizon-validation.json'),
                '--recordings', str(wrapper.h.ROOT / 'experiments/results/smoke/baseline/episodes')]
        with patch('sys.argv', args), patch('subprocess.run') as run, patch.object(wrapper.h, 'bounded') as bounded, contextlib.redirect_stdout(io.StringIO()) as output:
            wrapper.main()
        self.assertEqual(json.loads(output.getvalue())['stages'], [2, 12])
        run.assert_not_called()
        bounded.assert_not_called()

    def test_owned_container_caps_and_no_published_ports(self):
        command = wrapper.container_command(['bash', 'engine.sh'], 'own', 'internal', 'sha256:' + 'a' * 64)
        self.assertIn(f'nvidia.com/gpu={wrapper.h.GPU}', command)
        self.assertIn('--memory=28g', command)
        self.assertIn('--memory-swap=28g', command)
        self.assertIn('--pull=never', command)
        self.assertNotIn('-p', command)
        self.assertNotIn('--gpus', command)

    def test_failed_two_session_stage_prevents_twelve(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            calls = []
            def bounded(command, path, *args):
                calls.append(command)
                path.write_text(json.dumps({'passed': False, 'sessions_per_wave': 2, 'distinct_session_ids_verified': True}))
            with patch.object(wrapper.h, 'namespace_command', side_effect=lambda command: command), patch.object(wrapper.h, 'bounded', side_effect=bounded), self.assertRaises(ValueError):
                wrapper.run_stages(self.plan(), '172.25.0.2', 'sha256:' + 'a' * 64, Path(directory), {}, lambda path: None)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][calls[0].index('--sessions') + 1], '2')

    def test_deadline_refuses_before_docker(self):
        with patch.object(wrapper.sys, 'platform', 'linux'), patch.object(Path, 'resolve', return_value=wrapper.h.ROOT / 'experiments/qualify_images.py'), patch.object(wrapper.time, 'time', return_value=wrapper.h.DEADLINE), patch('subprocess.run') as run:
            with self.assertRaises(ValueError):
                wrapper.execute(self.plan())
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
