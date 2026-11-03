import datetime as dt
import json
import contextlib
import io
import pathlib
import unittest
from guard import decision, optional_deadline, main
from types import SimpleNamespace
from unittest.mock import patch


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((pathlib.Path(__file__).parent / "policy.json").read_text())
        self.policy["deadline"] = "2026-11-03T08:30:00+01:00"
        self.deadline = dt.datetime.fromisoformat(self.policy["deadline"]).timestamp()
        self.now = self.deadline - 3600
        self.snapshot = {"collected_at": self.now, "remaining_percent": [66]}

    def check(self, snapshot=None, **kw):
        return decision(self.policy, self.snapshot if snapshot is None else snapshot, self.now, **kw)[0]

    def test_valid_snapshot_allows_work(self):
        self.assertTrue(self.check())

    def test_any_shared_window_can_stop_work(self):
        self.snapshot["remaining_percent"] = [66, 25]
        self.assertFalse(self.check())

    def test_unknown_quota_fails_closed(self):
        self.assertFalse(self.check({}))
        self.assertFalse(self.check({"collected_at": self.now, "remaining_percent": []}))

    def test_expired_snapshot_stops_gpu(self):
        self.snapshot["collected_at"] -= 421
        self.assertFalse(self.check(gpu=True))

    def test_deadline_has_shutdown_buffer(self):
        self.now = self.deadline - 120
        self.snapshot["collected_at"] = self.now
        self.assertFalse(self.check())
        self.assertTrue(self.check(gpu=True))
        self.now = self.deadline - 45
        self.assertFalse(self.check(gpu=True))

    def test_null_deadline_allows_later_fresh_work_but_keeps_quota_stop(self):
        self.policy['deadline'] = None
        self.now = self.deadline + 86400
        self.snapshot['collected_at'] = self.now
        self.assertTrue(self.check())
        self.assertTrue(self.check(gpu=True))
        self.snapshot['remaining_percent'] = [25]
        self.assertFalse(self.check())
        self.assertFalse(self.check(stopped=True))

    def test_invalid_deadlines_fail_closed(self):
        for value in (False, 0, {}, [], '', 'not-a-date', '2026-11-03T08:30:00'):
            self.policy['deadline'] = value
            self.assertFalse(self.check(), repr(value))
        self.assertIsNone(optional_deadline(None))

    def test_all_usage_windows_must_be_valid(self):
        for windows in ([63, float('nan')], [63, float('inf')], [True], ['63']):
            self.snapshot['remaining_percent'] = windows
            self.assertFalse(self.check())

    def test_null_deadline_keeps_disk_reserve_guard(self):
        self.policy['deadline'] = None
        with patch('guard.read_state', return_value=(self.policy, self.snapshot)), patch('guard.time.time', return_value=self.now), patch('guard.pathlib.Path.exists', return_value=False), patch('guard.shutil.disk_usage', return_value=SimpleNamespace(free=0)), patch('sys.argv', ['guard.py', 'check']), contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as exit_status:
                main()
        self.assertEqual(exit_status.exception.code, 2)
        self.assertEqual(json.loads(output.getvalue())['reason'], 'disk reserve reached')

    def test_manual_stop_is_respected(self):
        self.assertFalse(self.check(stopped=True))


if __name__ == "__main__":
    unittest.main()
