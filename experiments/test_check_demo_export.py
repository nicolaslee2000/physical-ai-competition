import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import check_demo_export as check

HERE = Path(__file__).parent


class ConversionTests(unittest.TestCase):
    def test_all_source_hashes_and_paths_verified(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            root = Path(directory).resolve()
            source = root / 'source'
            source.mkdir()
            objects = []
            for index in range(170):
                relative = f'000/000/{index}.parquet'
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'pilot')
                objects.append({'relative_path': relative, 'bytes': 5, 'sha256': hashlib.sha256(b'pilot').hexdigest()})
            manifest = root / 'manifest.json'
            raw = json.dumps({'objects': objects}).encode()
            manifest.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            self.assertEqual(check.verify_source(source, manifest, digest, root)['source_objects_verified'], 170)
            (source / objects[0]['relative_path']).write_bytes(b'changed')
            with self.assertRaises(ValueError):
                check.verify_source(source, manifest, digest, root)
            with self.assertRaises(ValueError):
                check.owned(source / '../../outside', root)
            link = root / 'linked'
            link.symlink_to(source, target_is_directory=True)
            with self.assertRaises(ValueError):
                check.owned(link, root)

    def metadata(self):
        info = {'fps': 15, 'total_episodes': 10, 'total_frames': 30, 'features': {'action': {'shape': [17]}}}
        modality = {'state': {}, 'action': {}, 'video': {'wrist': {}}, 'annotation': {'task': {}}}
        position = 0
        for name, dimension in check.DIMS.items():
            info['features'][name] = {'shape': [dimension]}
            modality['state'][name] = {'start': 0, 'end': dimension}
            modality['action'][name] = {'start': position, 'end': position + dimension}
            position += dimension
        return info, modality, [{'episode_index': i, 'length': 3} for i in range(10)]

    def test_recipe_feature_episode_and_finite_action_guards(self):
        info, modality, episodes = self.metadata()
        self.assertEqual(check.check_metadata(info, modality, episodes), 30)
        for fps in (14, 30):
            with self.assertRaises(ValueError):
                check.check_metadata({**info, 'fps': fps}, modality, episodes)
        episodes[0]['length'] = 0
        with self.assertRaises(ValueError):
            check.check_metadata(info, modality, episodes)
        for action in ([0.] * 16, [float('nan')] * 17, [None] * 17):
            with self.assertRaises(ValueError):
                check.finite_action(action)
        check.finite_action([0.] * 17)

    def test_actual_shell_environment_uses_separate_task_root_paths(self):
        script = (HERE.parent / 'control/convert-molmo-demos.sh').read_text()
        block = script[script.index('export UV_PROJECT_ENVIRONMENT='):script.index('# Refuse cache/env paths')]
        result = subprocess.run(['bash', '-c', 'task_root="$1"\n' + block + '\nenv', 'env-test', str(check.ROOT)],
                                env={'PATH': '/usr/bin:/bin'}, capture_output=True, text=True, check=True)
        env = dict(line.split('=', 1) for line in result.stdout.splitlines())
        self.assertEqual(env['UV_PROJECT_ENVIRONMENT'], str(check.ROOT / 'conversion/.venv'))
        self.assertNotEqual(env['UV_PROJECT_ENVIRONMENT'], str(check.ROOT / 'positronic/.venv'))
        self.assertNotIn('HOME', env)
        self.assertNotIn('CODEX_HOME', env)
        for key in ('HF_HOME', 'TORCH_HOME', 'UV_CACHE_DIR', 'UV_PYTHON_INSTALL_DIR', 'TMPDIR'):
            self.assertTrue(Path(env[key]).is_relative_to(check.ROOT))
        self.assertEqual(env['CUDA_VISIBLE_DEVICES'], '')


if __name__ == '__main__':
    unittest.main()
