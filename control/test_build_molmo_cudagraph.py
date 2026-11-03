"""Execute only embedded filesystem validation; never invoke Docker or services."""
import hashlib
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).parent
SCRIPT=(HERE/'build-molmo-cudagraph.sh').read_text()
code=SCRIPT.split("<<'VALIDATE'\n",1)[1].split('\nVALIDATE',1)[0]
namespace={'__name__':'test_only'}
exec(compile(code,'build-preflight','exec'),namespace)


class BuildPreflightTests(unittest.TestCase):
    def fixture(self,root):
        source=root/'experiments/candidates/Dockerfile.molmoact2-cudagraphs'
        source.parent.mkdir(parents=True)
        source.write_bytes((HERE.parent/'experiments/candidates/Dockerfile.molmoact2-cudagraphs').read_bytes())
        (root/'tmp').mkdir();(root/'state').mkdir()
        return source

    def test_reviewed_source_passes_and_changed_instruction_fails(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            root=Path(directory).resolve();source=self.fixture(root)
            self.assertEqual(namespace['validate'](root),source)
            source.write_text('FROM '+namespace['BASE']+'\nCOPY . /unsafe\n')
            with self.assertRaises(ValueError):namespace['validate'](root)
            with self.assertRaises(ValueError):namespace['validate'](root,hashlib.sha256(source.read_bytes()).hexdigest())

    def test_external_context_symlink_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            root=Path(directory).resolve();self.fixture(root)
            (root/'tmp').rmdir();(root/'tmp').symlink_to('/tmp',target_is_directory=True)
            with self.assertRaises(ValueError):namespace['validate'](root)


if __name__=='__main__':unittest.main()
