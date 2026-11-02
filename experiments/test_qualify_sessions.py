"""Offline lifecycle/result guards; no model, network, recordings or GPU loaded."""
import unittest
from types import SimpleNamespace

import qualify_sessions as qualify


def row(index=0):
    return {'worker': index, 'passed': True, 'waves': [
        {'session_id': f'{index}-wave-{wave}', 'infer_ms': [20.0, 40.0],
         'validated_command_steps': 2, 'end_session_acknowledged': True} for wave in range(2)]}


class QualificationTests(unittest.TestCase):
    def test_credentials_mutable_images_and_query_rejected(self):
        immutable = 'sha256:' + 'a' * 64
        self.assertEqual(qualify.validate_identity('ws://172.25.0.2:8000', immutable), ('172.25.0.2', 8000))
        for url in ('ws://user:secret@localhost:8000', 'ws://localhost:8000?token=secret', 'https://localhost'):
            with self.assertRaises(ValueError):
                qualify.validate_identity(url, immutable)
        with self.assertRaises(ValueError):
            qualify.validate_identity('ws://localhost:8000', 'repo:latest')

    def test_complete_reopen_session_ids_and_queue_latency(self):
        result = qualify.aggregate([row(0), row(1)], 2)
        self.assertTrue(result['passed'])
        self.assertTrue(result['distinct_session_ids_verified'])
        self.assertEqual(result['calls'], 8)
        self.assertEqual((result['p50_ms'], result['p95_ms'], result['max_ms']), (30, 40, 40))

    def test_duplicate_reopened_or_concurrent_ids_fail_closed(self):
        rows = [row(0), row(1)]
        rows[1]['waves'][1]['session_id'] = rows[0]['waves'][0]['session_id']
        self.assertFalse(qualify.aggregate(rows, 2)['passed'])
        self.assertFalse(qualify.aggregate([row(0)], 2)['passed'])

    def test_timeout_and_invalid_worker_output_fail_closed(self):
        value = row()
        value['passed'] = False
        value['error_type'] = 'TimeoutError'
        self.assertFalse(qualify.aggregate([value], 1)['passed'])
        value = row()
        value['waves'][0]['infer_ms'][1] = 15001
        self.assertFalse(qualify.aggregate([value], 1)['passed'])
        self.assertIsNone(qualify.aggregate([], 1)['max_ms'])
        value = row()
        value['waves'][0]['end_session_acknowledged'] = False
        self.assertFalse(qualify.aggregate([value], 1)['passed'])
        value = row()
        value['waves'][0]['infer_ms'] = [20]
        self.assertFalse(qualify.aggregate([value], 1)['passed'])

    def test_droid_robot_type_required_before_array_validation(self):
        keys = SimpleNamespace(ROBOT_COMMAND='arm', GRIP='grip')
        class JointPosition:
            pass
        with self.assertRaises(ValueError):
            qualify.validate_commands({'arm': {'positions': [0] * 7}, 'grip': 0}, keys, JointPosition, None)
        with self.assertRaises(ValueError):
            qualify.validate_commands({'arm': JointPosition()}, keys, JointPosition, None)


if __name__ == '__main__':
    unittest.main()
