import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('prep',Path(__file__).with_name('prepare-placement-assets.py'))
prep=importlib.util.module_from_spec(spec);spec.loader.exec_module(prep)


class PlacementAssetsTests(unittest.TestCase):
    def fixture(self):
        cohort={'benchmark':prep.BENCHMARK,'episodes':[{'episode_index':i} for i in range(21,31)]}
        manifest=[{'house_index':i,'scene_dataset':'procthor-objaverse','data_split':'val'} for i in range(1000)]
        return cohort,manifest

    def test_only_exact_ten_frozen_houses_selected(self):
        cohort,manifest=self.fixture()
        packages=prep.selected_packages(cohort,manifest)
        self.assertEqual(len(packages),10)
        self.assertEqual(packages['procthor-objaverse-val_val_21.tar.zst'],[21])

    def test_other_family_split_duplicate_and_old_episode_rejected(self):
        for kind in ('benchmark','split','duplicate','old'):
            cohort,manifest=self.fixture()
            if kind=='benchmark':cohort['benchmark']='other'
            if kind=='split':manifest[21]['data_split']='train'
            if kind=='duplicate':cohort['episodes'][0]['episode_index']=22
            if kind=='old':cohort['episodes'][0]['episode_index']=0
            with self.assertRaises(ValueError):prep.selected_packages(cohort,manifest)


if __name__=='__main__':unittest.main()
