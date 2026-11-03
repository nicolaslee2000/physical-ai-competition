import hashlib
import io
from pathlib import Path
import tempfile
import unittest

import download_molmo_demos as pilot

HERE = Path(__file__).parent


class DownloadTests(unittest.TestCase):
    def test_audit_has_ten_successful_disjoint_demonstrations(self):
        objects = pilot.audited_objects()
        self.assertEqual(len(objects), 170)
        self.assertEqual(sum(value is not None for value in objects.values()), 10)

    def test_foreign_traversal_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            root = Path(directory)
            for key in ('other/000/a', pilot.PREFIX + '../000/a', pilot.PREFIX + '000/000/../a', pilot.PREFIX + '000\\000/a'):
                with self.assertRaises(ValueError):
                    pilot.safe_target(root, key)
            (root / '000').symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                pilot.safe_target(root, pilot.PREFIX + '000/000/meta.json')

    def test_size_hash_and_atomicity_guards(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            target = Path(directory) / 'object'
            raw = b'public pilot'
            digest = hashlib.sha256(raw).hexdigest()
            self.assertEqual(pilot.stream_object(io.BytesIO(raw), target, len(raw), 100, digest), (digest, len(raw)))
            for size, budget, sha in ((len(raw), 100, '0' * 64), (len(raw) - 1, 100, digest), (len(raw), 1, digest)):
                with self.assertRaises(ValueError):
                    pilot.stream_object(io.BytesIO(raw), target, size, budget, sha)
                self.assertEqual(target.read_bytes(), raw)
                self.assertEqual(list(Path(directory).glob('*.partial-*')), [])


if __name__ == '__main__':
    unittest.main()
