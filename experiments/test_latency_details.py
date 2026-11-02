"""OTLP fixtures match upstream telemetry.py and test_timing_report.py."""
import json
from pathlib import Path
import tempfile
import unittest

import latency_details as audit

HERE = Path(__file__).parent


def span(name, identity, start_ms, end_ms, parent='', attrs=None):
    encoded = []
    for key, value in (attrs or {}).items():
        encoded.append({'key': key, 'value': {'boolValue' if isinstance(value, bool) else 'intValue': value}})
    return {'name': name, 'spanId': identity, 'traceId': 'a' * 32,
            'parentSpanId': parent, 'startTimeUnixNano': str(int((100000 + start_ms) * 1e6)),
            'endTimeUnixNano': str(int((100000 + end_ms) * 1e6)), 'attributes': encoded}


def doc(spans):
    return {'resourceSpans': [{'resource': {'attributes': [
        {'key': 'process.name', 'value': {'stringValue': 'harness'}},
        {'key': 'run.id', 'value': {'stringValue': 'run-1'}}]},
        'scopeSpans': [{'spans': spans}]}]}


def fixture():
    return [span('eval.pass', 'pass', 0, 30000),
            span('episode', 'ep0', 1, 22000, 'pass', {'episode.index': 0}),
            span('policy.submit', 'nested', 2, 21000, 'ep0'),
            span('policy.infer', 'cold', 3, 20003, 'nested'),
            span('policy.infer', 'steady0', 20004, 20024, 'ep0'),
            span('episode', 'ep1', 22001, 29000, 'pass', {'episode.index': 1}),
            span('policy.infer', 'steady1', 22002, 22042, 'ep1')]


class AuditTests(unittest.TestCase):
    def run_fixture(self, spans, tail=''):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            telemetry = Path(directory) / 'episodes/telemetry'
            telemetry.mkdir(parents=True)
            (telemetry / 'harness.spans.jsonl').write_text(json.dumps(doc(spans)) + '\n' + tail)
            return audit.report(Path(directory), 2)

    def test_first_warmup_steady_max_and_worst_episode(self):
        result = self.run_fixture(fixture())
        self.assertTrue(result['trace_complete'], result['issues'])
        self.assertEqual(result['first_inference']['duration_ms'], 20000)
        self.assertEqual(result['observed_warmup']['calls'], 1)
        self.assertEqual(result['observed_steady'], {'calls': 2, 'p50_ms': 30, 'p95_ms': 39, 'max_ms': 40})
        self.assertEqual(result['observed_all']['max_ms'], 20000)
        self.assertEqual(result['worst_episode_by_max_inference']['episode_index'], 0)
        self.assertEqual(result['episodes'][1]['first_inference']['duration_ms'], 40)
        self.assertFalse(result['observed_all_calls_within_15s'])

    def test_missing_pass_incomplete_even_with_closed_episodes(self):
        result = self.run_fixture(fixture()[1:])
        self.assertFalse(result['trace_complete'])
        self.assertIsNone(result['observed_all_calls_within_15s'])

    def test_truncated_line_and_partial_episode_flagged(self):
        spans = fixture()
        spans[1]['attributes'].append({'key': 'episode.partial', 'value': {'boolValue': True}})
        result = self.run_fixture(spans, '{"resourceSpans":')
        self.assertFalse(result['trace_complete'])
        self.assertTrue(any('malformed/incomplete' in issue for issue in result['issues']))
        self.assertIn('Partial episode span', result['issues'])

    def test_missing_episode_inference_flagged(self):
        result = self.run_fixture(fixture()[:-1])
        self.assertFalse(result['trace_complete'])
        self.assertTrue(any('has no inference' in issue for issue in result['issues']))

    def test_missing_files_and_failed_pass_flagged(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            result = audit.report(Path(directory), 20)
        self.assertFalse(result['trace_complete'])
        self.assertEqual(result['observed_all']['calls'], 0)
        spans = fixture()
        spans[0]['attributes'].append({'key': 'pass.failed', 'value': {'boolValue': True}})
        self.assertIn('Pass marked failed', self.run_fixture(spans)['issues'])

    def test_cycle_and_duplicate_spans_not_silently_counted(self):
        spans = fixture()
        spans[2]['parentSpanId'] = 'nested'
        self.assertIn('Inference has no recorded ancestor episode', self.run_fixture(spans)['issues'])
        result = self.run_fixture(fixture() + [fixture()[-1]])
        self.assertFalse(result['trace_complete'])


if __name__ == '__main__':
    unittest.main()
