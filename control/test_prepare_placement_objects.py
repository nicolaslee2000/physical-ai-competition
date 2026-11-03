import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('objects',Path(__file__).with_name('prepare-placement-objects.py'))
objects=importlib.util.module_from_spec(spec);spec.loader.exec_module(objects)


class ObjectRecoveryTests(unittest.TestCase):
    def test_exact_uid_archive_mapping(self):
        uid=objects.FIRST_UID
        self.assertEqual(objects.archive_for_objaverse(f'{uid}/{uid}_visual.obj'),f'objaverse_{uid}.tar.zst')
        for relative in ('../escape','wrong/object.obj'):
            with self.assertRaises(ValueError):objects.archive_for_objaverse(relative)

    def test_references_deduplicate_without_downloads(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root=Path(directory).resolve();assets=root/'assets';scene=assets/'scenes/source/val_1.xml'
            scene.parent.mkdir(parents=True)
            ref=f'../../objects/objaverse/{objects.FIRST_UID}/{objects.FIRST_UID}_visual.obj'
            scene.write_text(f'<mujoco><asset><mesh file="{ref}"/><mesh file="{ref}"/></asset></mujoco>')
            with patch.object(objects,'ROOT',root):
                found,other=objects.scene_refs([scene],assets)
            self.assertEqual(len(found['objaverse']),1);self.assertEqual(other,[])
            scene.write_text('<mujoco><mesh file="../../../../outside.obj"/></mujoco>')
            with patch.object(objects,'ROOT',root),self.assertRaises(ValueError):objects.scene_refs([scene],assets)


if __name__=='__main__':unittest.main()
