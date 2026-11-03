"""Artifact and config tests without Torch, model loading, networking or a server."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from .serve import verify_artifacts, local_tokenizer_config


class ServeTests(unittest.TestCase):
    def test_artifact_size_sha256_git_blob_and_path_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();data=root/'artifacts';data.mkdir()
            raw=b'fixture';path=data/'tokenizer.json';path.write_bytes(raw)
            pins={'weights_revision':'pinned','tokenizer':{'revision':'pinned'},'artifacts':[
                {'path':'tokenizer.json','size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                 'git_blob_sha1':hashlib.sha1(b'blob 7\0'+raw).hexdigest()}]}
            self.assertEqual(verify_artifacts(data,pins,root)['verified_artifacts'],1)
            extra=data/'unreviewed-file';extra.write_bytes(b'extra')
            with self.assertRaises(ValueError):verify_artifacts(data,pins,root)
            extra.unlink()
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):verify_artifacts(data,pins,root)
            pins['artifacts'][0]['path']='../escape'
            with self.assertRaises(ValueError):verify_artifacts(data,pins,root)

    def test_tokenizer_identifier_is_local_not_merely_cache_dir(self):
        config={'model':{'llm':{'tokenizer':{'identifier':'Qwen/Qwen3-4B-Instruct-2507','tokenizer_dir':None}},'other':[1,2]}}
        actual=local_tokenizer_config(config,Path('/local/tokenizer'),Path('/local/cache'))
        self.assertEqual(actual['model']['llm']['tokenizer']['identifier'],'/local/tokenizer')
        self.assertEqual(actual['model']['llm']['tokenizer']['tokenizer_dir'],'/local/cache')
        self.assertEqual(actual['model']['other'],[1,2])
        self.assertIsNone(config['model']['llm']['tokenizer']['tokenizer_dir'])
        config['model']['llm']['tokenizer']['identifier']='other'
        with self.assertRaises(ValueError):local_tokenizer_config(config,Path('/local'),Path('/cache'))


if __name__=='__main__':unittest.main()
