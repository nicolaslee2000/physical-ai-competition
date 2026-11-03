"""Offline prompt-sweep coverage, isolation and conservative memory gates."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import qualify_prompts as q
import qualify_sessions as sessions
from test_qualify_sessions import row


def report(indices):
    rows = [row(i) for i in range(len(indices))]
    for worker in rows:
        for wave in worker['waves']:
            wave['validated_inference_results'] = 2
    value = sessions.aggregate(rows, len(indices))
    value['prompts'] = [q.prompt_metadata(i) for i in indices]
    return value


class PromptTests(unittest.TestCase):
    def test_override_preserves_sensors_without_mutation(self):
        frame = object()
        obs = {'task': 'original', 'joints': [1], 'image.exterior': frame}
        self.assertIs(sessions.apply_task_override(obs, None), obs)
        overridden = sessions.apply_task_override(obs, 'pick blue object')
        self.assertEqual(obs['task'], 'original')
        self.assertEqual(overridden['task'], 'pick blue object')
        self.assertIs(overridden['image.exterior'], frame)
        for invalid in ('', ' ', 42, 'word ' * 129):
            with self.assertRaises(ValueError):
                sessions.apply_task_override(obs, invalid)
        with self.assertRaises(ValueError):
            sessions.qualify('unused', 8000, 'unused', 12, 2, ['short'])

    def test_distinct_alternating_shapes_and_no_text_in_metadata(self):
        metadata = [q.prompt_metadata(i) for i in range(12)]
        self.assertEqual(len({row['sha256'] for row in metadata}), 12)
        for index, item in enumerate(metadata):
            self.assertEqual(item['words'], q.LENGTHS[index])
            self.assertTrue(1 <= item['words'] <= 128)
            self.assertTrue(all(word.isalpha() for word in q.synthetic_prompt(index).split()))
            self.assertEqual(set(item), {'index', 'words', 'characters', 'sha256'})
            self.assertTrue(item['words'] < 20 if index % 2 == 0 else item['words'] >= 80)

    def test_checks_lifecycle_prompt_identity_and_consumed_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.json'
            for indices in ([0], list(range(12))):
                value = report(indices)
                path.write_text(json.dumps(value))
                self.assertTrue(q.checked_prompt_report(path, indices)['passed'])
                for mutation in ('failed', 'hash', 'missing_result', 'duplicate_worker'):
                    value = report(indices)
                    if mutation == 'failed':
                        value['passed'] = False
                    elif mutation == 'hash':
                        value['prompts'][0]['sha256'] = 'bad'
                    elif mutation == 'missing_result':
                        value['workers'][0]['waves'][1]['validated_inference_results'] = 1
                    else:
                        value['workers'][0]['worker'] = 99
                    path.write_text(json.dumps(value))
                    with self.assertRaises(ValueError):
                        q.checked_prompt_report(path, indices)

    def test_sparse_memory_never_claims_peak_compliance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'resources.jsonl'
            self.assertIsNone(q.memory_report(path)['passed'])
            def sample(mib, gpu=q.images.h.GPU):
                return json.dumps({'gpu_card': {'returncode': 0, 'sample': f'{gpu}, {mib}, 97887, 0'}}) + '\n'
            path.write_text(sample(18000) + sample(95000, 'other-GPU'))
            gate = q.memory_report(path)
            self.assertIsNone(gate['passed'])
            self.assertEqual(gate['samples'], 1)
            self.assertGreater(gate['sampled_headroom_bytes'], 0)
            path.write_text(sample(22000))
            self.assertFalse(q.memory_report(path)['passed'])
            self.assertEqual(q.memory_report(path)['budget_bytes'], 22_000_000_000)

    def test_failed_prompt_stops_before_concurrent_stage_preserves_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            def failed(command, output, *unused):
                value = report([0]); value['passed'] = False
                output.write_text(json.dumps(value))
            with patch.object(q.images.h, 'namespace_command', side_effect=lambda command: command), patch.object(q.images.h, 'bounded', side_effect=failed) as call:
                with self.assertRaises(ValueError):
                    q.run_sweep({'python': 'python', 'repo': tmp, 'recordings': tmp}, '172.25.0.2', 'sha256:'+'a'*64, directory, {}, lambda path: None)
                self.assertEqual(call.call_count, 1)
            summary = json.loads((directory / 'prompt-sweep-summary.json').read_text())
            self.assertFalse(summary['functional_passed'])
            self.assertFalse(summary['ready_for_fresh_validation'])
            self.assertIsNone(summary['memory_gate']['passed'])

    def test_full_sweep_requires_ten_serial_then_distinct_twelve(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            def succeed(command, output, *unused):
                indices = list(range(12)) if '--concurrent' in command else [int(command[command.index('--prompt-index')+1])]
                output.write_text(json.dumps(report(indices)))
            with patch.object(q.images.h, 'namespace_command', side_effect=lambda command: command), patch.object(q.images.h, 'bounded', side_effect=succeed) as call:
                result = q.run_sweep({'python': 'python', 'repo': tmp, 'recordings': tmp}, '172.25.0.2', 'sha256:'+'a'*64, directory, {}, lambda path: None)
            self.assertEqual(call.call_count, 11)
            self.assertTrue(result['prompt_sweep']['functional_passed'])
            self.assertEqual(result['prompt_sweep']['concurrent_12']['sessions_per_wave'], 12)
            self.assertFalse(result['qualification_passed'])


if __name__ == '__main__':
    unittest.main()
