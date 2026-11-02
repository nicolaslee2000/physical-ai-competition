import datetime as dt
import json
import pathlib
import unittest
from guard import decision


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((pathlib.Path(__file__).parent / "policy.json").read_text())
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

    def test_manual_stop_is_respected(self):
        self.assertFalse(self.check(stopped=True))


if __name__ == "__main__":
    unittest.main()
