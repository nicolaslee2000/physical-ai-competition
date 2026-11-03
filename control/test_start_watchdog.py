"""Execute the actual shell entrypoint against fake service commands; no real services touched."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).parent


class WatchdogTests(unittest.TestCase):
    def run_script(self, deadline, active=True):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            root = Path(directory)
            control, binary = root / 'control', root / 'bin'
            control.mkdir()
            binary.mkdir()
            for name in ('guard.py', 'start-watchdog.sh'):
                shutil.copyfile(HERE / name, control / name)
            (control / 'policy.json').write_text(json.dumps({'deadline': deadline, 'stop_gpu_seconds_before_deadline': 45}))
            fake = '''#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
if name != 'flock':
    with open(os.environ['CALL_LOG'], 'a') as log:
        log.write(json.dumps([name, *sys.argv[1:]]) + '\\n')
if name == 'systemctl' and 'show' in sys.argv:
    print('loaded')
if name == 'systemctl' and 'is-active' in sys.argv:
    raise SystemExit(0 if os.environ['WATCHDOG_ACTIVE'] == '1' else 3)
'''
            for name in ('systemctl', 'systemd-run', 'flock'):
                path = binary / name
                path.write_text(fake)
                path.chmod(0o755)
            log = root / 'calls.jsonl'
            env = dict(os.environ, PATH=str(binary) + ':' + os.environ['PATH'], CALL_LOG=str(log), WATCHDOG_ACTIVE=str(int(active)))
            result = subprocess.run(['bash', str(control / 'start-watchdog.sh')], env=env, capture_output=True, text=True, timeout=10)
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return result, calls

    def test_null_cancels_only_own_deadline_and_keeps_active_watcher(self):
        result, calls = self.run_script(None)
        self.assertEqual(result.returncode, 0, result.stderr)
        stops = [call for call in calls if call[:3] == ['systemctl', '--user', 'stop']]
        self.assertEqual([call[-1] for call in stops], ['nick-physical-ai-deadline.timer', 'nick-physical-ai-deadline.service'])
        self.assertFalse(any(call[0] == 'systemd-run' for call in calls))

    def test_null_starts_missing_watcher_without_deadline_timer(self):
        result, calls = self.run_script(None, active=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        starts = [call for call in calls if call[0] == 'systemd-run']
        self.assertEqual(len(starts), 1)
        self.assertIn('--unit=nick-physical-ai-watchdog', starts[0])

    def test_finite_deadline_schedules_timer_with_policy_shutdown_margin(self):
        result, calls = self.run_script('2026-11-03T07:30:00+00:00')
        self.assertEqual(result.returncode, 0, result.stderr)
        starts = [call for call in calls if call[0] == 'systemd-run']
        self.assertEqual(len(starts), 1)
        self.assertIn('--unit=nick-physical-ai-deadline', starts[0])
        self.assertIn('--on-calendar=2026-11-03 07:29:15 UTC', starts[0])

    def test_invalid_deadline_does_not_change_service_state(self):
        for deadline in (False, 'bad-date', '2026-11-03T07:30:00'):
            result, calls = self.run_script(deadline)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
