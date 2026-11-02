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

    def test_namespace_prefix_uses_task_daemon_only(self):
        with patch.object(Path, 'read_text', return_value='1234\n'):
            command = harness.namespace_command(['/usr/bin/curl', 'target'])
        self.assertEqual(command, ['/usr/bin/nsenter', '--user=/proc/1234/ns/user',
                                  '--mount=/proc/1234/ns/mnt', '--preserve-credentials',
                                  '/usr/bin/nsenter', f'--net={harness.ROOT}/runtime/dockerd-rootless/netns',
                                  '/usr/bin/curl', 'target'])
        for pid in ('', '1', '0', '../escape', '123;echo'):
            with patch.object(Path, 'read_text', return_value=pid), self.assertRaises(ValueError):
                harness.namespace_command(['command'])

    def test_policy_address_comes_from_own_network(self):
        response = subprocess.CompletedProcess([], 0, stdout=json.dumps({
            'own-network': {'IPAddress': '172.25.0.2'}, 'unrelated': {'IPAddress': '172.30.0.3'}}))
        with patch('subprocess.run', return_value=response) as run:
            self.assertEqual(harness.policy_address(['bash', 'engine.sh'], 'owned-container', 'own-network', {}), '172.25.0.2')
        self.assertEqual(run.call_args.args[0][-1], 'owned-container')
        response.stdout = '{"own-network": {"IPAddress": "127.0.0.1"}}'
        with patch('subprocess.run', return_value=response), self.assertRaises(ValueError):
            harness.policy_address(['bash', 'engine.sh'], 'owned-container', 'own-network', {})

    def test_readiness_requires_actual_ip_200_and_contract_alive(self):
        for output, expected in (('{"alive_seconds": null}\n200', True),
                                 ('{"alive_seconds": 1}\n200', True),
                                 ('{"alive_seconds": 1.5}\n200', False),
                                 ('{"alive_seconds": true}\n200', False),
                                 ('{"alive_seconds": 1}\n404', False),
                                 ('unrelated service\n200', False),
                                 ('{"alive_seconds": "1"}\n200', False),
                                 ('{"status": "ok"}\n200', False)):
            response = subprocess.CompletedProcess([], 0, stdout=output)
            with patch.object(Path, 'read_text', return_value='1234'), patch('subprocess.run', return_value=response) as run:
                self.assertEqual(harness.policy_ready('172.25.0.2', {}), expected)
                command = run.call_args.args[0]
                self.assertEqual(command[-1], 'http://172.25.0.2:8000/api/v1/keepalive')
                self.assertEqual(command[0], '/usr/bin/nsenter')
                self.assertIn('--noproxy', command)

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
