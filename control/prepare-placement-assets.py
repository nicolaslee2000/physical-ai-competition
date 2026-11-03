#!/usr/bin/env python3
"""Prepare ONLY ten frozen placement-house scene packages over the ordinary host network.

Dry-run default. Execute later through start-job.sh using the installed MolmoSpaces
Python. Never calls ResourceManager.setup/install_all or downloads object collections.
"""
import argparse
import gzip
import hashlib
import json
import os
import multiprocessing as mp
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path('/opt/hderc-internal/nick/physical-ai-competition')
SOURCE = 'procthor-objaverse-val'
VERSION = '20251205_with_occupancy'
BENCHMARK = 'molmospaces-bench-v2/procthor-objaverse/FrankaPickandPlaceNextToHardBench/FrankaPickandPlaceNextToHardBench_20260305_json_benchmark'
CACHE = ROOT / 'cache/molmospaces'
ASSETS = ROOT / 'models/molmospaces/assets'


def owned(path):
    path = Path(path)
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError('Path outside task root')
    return path


def selected_packages(cohort, manifest):
    if cohort['benchmark'] != BENCHMARK or len(cohort['episodes']) != 10 or len(manifest) != 1000:
        raise ValueError('Require exact frozen NextToHard ten-episode cohort')
    indices = [row['episode_index'] for row in cohort['episodes']]
    if len(set(indices)) != 10 or any(type(index) is not int or not 21 <= index < 1000 for index in indices):
        raise ValueError('Invalid frozen episode indices')
    packages = {}
    for index in indices:
        record = manifest[index]
        house = record['house_index']
        if record['scene_dataset'] != 'procthor-objaverse' or record['data_split'] != 'val' or type(house) is not int or house < 0:
            raise ValueError('Unexpected scene source or house identity')
        packages.setdefault(f'{SOURCE}_val_{house}.tar.zst', []).append(index)
    return packages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=Path, default=ROOT / 'experiments/fresh-placement-cohort.json')
    parser.add_argument('--cohort-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    raw = owned(args.cohort).read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.cohort_sha256:
        raise ValueError('Frozen cohort SHA mismatch')
    cohort = json.loads(raw)
    manifest_raw = owned(cohort['manifest']['server_path']).read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != cohort['manifest']['sha256']:
        raise ValueError('Frozen benchmark manifest SHA mismatch')
    packages = selected_packages(cohort, json.loads(manifest_raw))
    from molmospaces_resources import ResourceManager, R2RemoteStorage, CompactPathTrie
    from molmospaces_resources.constants import REMOTE_MANIFEST_NAME, COMBINED_TRIES_NAME
    version_dir = owned(CACHE / 'scenes' / SOURCE / VERSION)
    sizes = json.loads((version_dir / REMOTE_MANIFEST_NAME).read_text())
    with gzip.open(version_dir / COMBINED_TRIES_NAME, 'rt') as stream:
        packed_tries = json.load(stream)
    leaves = {}
    for package in packages:
        if package not in sizes or package not in packed_tries:
            raise ValueError('Package absent from installed source metadata')
        leaves[package] = list(CompactPathTrie.from_dict(packed_tries[package]).leaf_paths())
        if not leaves[package]:
            raise ValueError('Empty package trie')
        for leaf in leaves[package]:
            if Path(leaf).is_absolute() or '..' in Path(leaf).parts:
                raise ValueError('Unsafe resource metadata path')
            owned(version_dir / leaf)
    plan = {'scope': 'exact frozen placement scene archives only; no object collection/model/GPU work',
            'cohort_sha256': args.cohort_sha256, 'source': SOURCE, 'version': VERSION,
            'cache_dir': str(version_dir), 'assets_dir': str(ASSETS),
            'packages': [{'package': package, 'episode_indices': indices, 'compressed_size_mb_hint': sizes[package],
                          'existing_leaf_files': sum((version_dir / leaf).is_file() for leaf in leaves[package]),
                          'expected_leaf_paths': len(leaves[package])} for package, indices in packages.items()]}
    print(json.dumps(plan, indent=2), flush=True)
    if not args.execute:
        return
    if sys.platform != 'linux' or Path(__file__).resolve() != ROOT / 'control/prepare-placement-assets.py' or not os.environ.get('INVOCATION_ID'):
        raise ValueError('Execute only from task root via start-job.sh')
    if os.getuid() != 1006 or os.environ.get('DOCKER_HOST', '').startswith('tcp:'):
        raise ValueError('Unexpected execution account/context')
    # No nsenter/Docker is used: downloads deliberately use ordinary host DNS/network.
    import requests
    class BoundedStorage(R2RemoteStorage):
        def __init__(self):
            super().__init__('mujoco-thor-resources')
            self.attempts, self.responses = {}, []
            self.http = requests.Session()
            self.http.trust_env = False  # Public URL: no proxy/netrc credential discovery.
        def fetch_file(self, *args, **kwargs):
            raise RuntimeError('Only existing cached manifests are authorized')
        def stream_archive(self, relative_path, package):
            if str(relative_path) != f'scenes/{SOURCE}/{VERSION}' or package not in packages:
                raise ValueError('Unselected package download denied')
            self.attempts[package] = self.attempts.get(package, 0) + 1
            if self.attempts[package] > 1:
                raise RuntimeError('One GET per isolated attempt; parent permits three attempts')
            response = self.http.get(f'{self.base_url}/{relative_path}/{package}', stream=True, timeout=(15, 90))
            response.raise_for_status()
            self.responses.append(response)
            return response.raw
    storage = BoundedStorage()
    manager = ResourceManager(storage, {'scenes': {SOURCE: VERSION}}, ASSETS, CACHE, force_install=False)
    archive = ROOT / 'state/archive' / ('placement-assets-' + uuid.uuid4().hex[:10])
    report = {**plan, 'results': []}
    def guard():
        subprocess.run([sys.executable, str(ROOT / 'control/guard.py'), 'check'], check=True, timeout=15)
    def install_attempt(package):
        context = mp.get_context('fork')
        parent, child = context.Pipe(duplex=False)
        def install():
            try:
                storage.attempts.clear()
                manager.install_packages('scenes', {SOURCE: [package]})
                child.send({'passed': True, 'gets': min(storage.attempts.get(package, 0), 1)})
            except BaseException as exc:
                child.send({'passed': False, 'error_type': type(exc).__name__, 'gets': min(storage.attempts.get(package, 0), 1)})
            finally:
                for response in storage.responses:
                    response.close()
                child.close()
        process = context.Process(target=install)
        process.start()
        child.close()
        process.join(timeout=900)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
            raise TimeoutError('Bounded house attempt exceeded 15 minutes')
        result = parent.recv() if parent.poll() else {'passed': False, 'error_type': 'MissingWorkerResult', 'gets': 1}
        parent.close()
        return result
    for package in packages:
        guard()  # Includes task disk reserve and fresh account-usage snapshot.
        paths = [version_dir / leaf for leaf in leaves[package]]
        flag = version_dir / ('.' + package.replace('/', '__') + '_complete_extract')
        missing = [path for path in paths if not path.exists()]
        ambiguous = [path for path in paths if path.exists() and (not path.is_file() or path.stat().st_size == 0)]
        if ambiguous:
            raise ValueError('Ambiguous existing package leaf; preserve it for explicit recovery review')
        if flag.exists() and missing:
            # A completion marker with demonstrably absent trie leaves is stale. Move ONLY that marker.
            owned(flag)
            archive.mkdir(parents=True, exist_ok=True)
            metadata = {'path': str(flag), 'sha256': hashlib.sha256(flag.read_bytes()).hexdigest(),
                        'size': flag.stat().st_size, 'mtime_ns': flag.stat().st_mtime_ns,
                        'missing_leaf_paths': [str(path) for path in missing]}
            (archive / (package + '.marker.json')).write_text(json.dumps(metadata, indent=2))
            flag.rename(archive / flag.name)
        try:
            gets = 0
            for attempt in range(3):
                guard()
                outcome = install_attempt(package)
                gets += outcome['gets']
                if outcome['passed']:
                    break
                if attempt == 2:
                    raise RuntimeError('Three bounded package attempts failed')
                time.sleep(2)
            if any(not path.is_file() or path.stat().st_size == 0 for path in paths) or not flag.is_file():
                raise ValueError('Package did not produce all expected files and completion marker')
            report['results'].append({'package': package, 'leaf_files': len(paths), 'download_attempts': gets, 'complete_marker': str(flag)})
        finally:
            for response in storage.responses:
                response.close()
            storage.responses.clear()
            archive.mkdir(parents=True, exist_ok=True)
            (archive / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        guard()


if __name__ == '__main__':
    main()
