"""Offline safety checks: no Docker, network, simulator or GPU is invoked."""
import contextlib
import io
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import local_eval as harness

HERE = Path(__file__).parent


class HarnessTests(unittest.TestCase):
    def test_foreign_and_traversal_paths_rejected(self):
        for path in ('relative', '/tmp/no', str(harness.ROOT / '../other')):
            with self.assertRaises(ValueError):
                harness.owned(path)

    def test_symlink_escape_rejected(self):
        with patch.object(Path, 'resolve', return_value=Path('/tmp/escaped')):
            with self.assertRaises(ValueError):
                harness.owned(harness.ROOT / 'escape')

    def test_environment_omits_credentials_and_uses_task_directories(self):
        with patch.dict('os.environ', {'API_KEY': 'private', 'SSH_AUTH_SOCK': 'private', 'DOCKER_HOST': 'private'}):
            env = harness.environment()
        for key in ('API_KEY', 'SSH_AUTH_SOCK', 'DOCKER_HOST', 'HOME', 'CODEX_HOME'):
            self.assertNotIn(key, env)
        for key in ('PHYSICAL_AI_CACHE_DIR', 'TMPDIR', 'HF_HOME', 'UV_CACHE_DIR', 'MLSPACES_CACHE_DIR'):
            harness.owned(env[key])
        self.assertEqual(env['CUDA_VISIBLE_DEVICES'], harness.GPU)

    def test_dry_run_has_no_process_or_network_calls(self):
        with patch.object(sys, 'argv', ['local_eval.py']), patch('subprocess.Popen') as spawn, \
                patch('subprocess.run') as run, contextlib.redirect_stdout(io.StringIO()) as output:
            harness.main()
        spawn.assert_not_called()
        run.assert_not_called()
        plan = json.loads(output.getvalue())
        self.assertEqual(len(plan['holdout']), 15)
        self.assertEqual(plan['gpu'], harness.GPU)

    def test_timed_out_process_is_reaped(self):
        # Real short-lived child process verifies timeout cleanup without server resources.
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            real_killpg = os.killpg
            def terminate_group(pid, sig):
                # macOS execution policy restricts SIGKILL; the child exits on SIGTERM.
                if sig == signal.SIGTERM:
                    real_killpg(pid, sig)
            with patch('os.killpg', side_effect=terminate_group) as kill, self.assertRaises(subprocess.TimeoutExpired):
                harness.bounded([sys.executable, '-c', 'import time; time.sleep(30)'],
                                Path(directory) / 'timeout.log', harness.environment(), 0.05, HERE)
            self.assertEqual([call.args[1] for call in kill.call_args_list], [signal.SIGTERM, signal.SIGKILL])


if __name__ == '__main__':
    unittest.main()
