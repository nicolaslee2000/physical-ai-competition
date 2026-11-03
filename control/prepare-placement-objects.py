#!/usr/bin/env python3
"""Dry-run exact frozen-house object-reference recovery; --execute only via start-job.sh."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

ROOT = Path('/opt/hderc-internal/nick/physical-ai-competition')
ASSETS = ROOT / 'models/molmospaces/assets'
CACHE = ROOT / 'cache/molmospaces'
VERSIONS = {'objaverse': '20260131', 'thor': '20251117'}
FIRST_UID = '393a37854b3d4f2abb277b18d5bc4fdb'


def owned(path):
    path = Path(path)
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError('Reference escapes task root')
    return path


def scene_refs(paths, assets=ASSETS):
    objects, other_missing, seen = {}, [], set()
    pending = list(paths)
    while pending:
        path = pending.pop()
        if str(path) in seen:
            continue
        seen.add(str(path))
        owned(path)
        for element in ET.parse(path).iter():
            value = element.get('file')
            if not value:
                continue
            reference = Path(os.path.normpath(str(path.parent / value)))
            owned(reference)
            try:
                relative = reference.relative_to(assets / 'objects')
            except ValueError:
                if not reference.exists():
                    other_missing.append(str(reference))
            else:
                source = relative.parts[0]
                if source not in VERSIONS:
                    raise ValueError('Unexpected object source')
                objects.setdefault(source, set()).add(str(Path(*relative.parts[1:])))
            if element.tag == 'include' and reference.is_file() and reference.suffix == '.xml':
                pending.append(reference)
    return objects, sorted(set(other_missing))


def archive_for_objaverse(relative):
    uid = Path(relative).parts[0]
    if not re.fullmatch('[a-f0-9]{32}', uid):
        raise ValueError('Unexpected Objaverse UID reference')
    return f'objaverse_{uid}.tar.zst'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=Path, default=ROOT / 'experiments/fresh-placement-cohort.json')
    parser.add_argument('--cohort-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    # Reuse the reviewed exact ten-house selection logic, without running its main/setup.
    spec = importlib.util.spec_from_file_location('scene_prep', Path(__file__).with_name('prepare-placement-assets.py'))
    scene = importlib.util.module_from_spec(spec); spec.loader.exec_module(scene)
    raw = owned(args.cohort).read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.cohort_sha256:
        raise ValueError('Frozen cohort SHA mismatch')
    cohort = json.loads(raw)
    manifest_raw = owned(cohort['manifest']['server_path']).read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != cohort['manifest']['sha256']:
        raise ValueError('Benchmark manifest SHA mismatch')
    houses = scene.selected_packages(cohort, json.loads(manifest_raw))
    house_paths = [ASSETS / 'scenes/procthor-objaverse-val' / (package.removeprefix('procthor-objaverse-val_').removesuffix('.tar.zst') + '.xml') for package in houses]
    references, other_missing = scene_refs(house_paths)
    from molmospaces_resources import CompactPathTrie, PickleLMDBMap, ResourceManager, R2RemoteStorage
    from molmospaces_resources.constants import REMOTE_MANIFEST_NAME, COMBINED_TRIES_NAME
    tries, sizes, selected, unresolved = {}, {}, {}, []
    for source, version in VERSIONS.items():
        destination = owned(CACHE / 'objects' / source / version)
        if (ASSETS / 'objects' / source).resolve() != destination:
            raise ValueError('Installed object source version differs; explicit review required')
        sizes[source] = json.loads((destination / REMOTE_MANIFEST_NAME).read_text())
        db = ASSETS / '.lmdb/objects' / source
        if (db / 'data.mdb').is_file():
            tries[source] = PickleLMDBMap(db, readonly=True)
        elif source == 'thor':
            with gzip.open(destination / COMBINED_TRIES_NAME, 'rt') as file:
                tries[source] = {name: CompactPathTrie.from_dict(value) for name, value in json.load(file).items()}
        else:
            raise ValueError('Readonly Objaverse index missing; do not rebuild the entire index in this audit')
        for relative in sorted(references.get(source, [])):
            candidates = [archive_for_objaverse(relative)] if source == 'objaverse' else sorted(tries[source])
            match = next((name for name in candidates if name in sizes[source] and name in tries[source] and tries[source][name].exists(relative)), None)
            if match is None:
                unresolved.append({'source': source, 'reference': relative, 'version': version})
            else:
                selected.setdefault((source, match), []).append(relative)
    rows = []
    for (source, package), files in sorted(selected.items()):
        destination = CACHE / 'objects' / source / VERSIONS[source]
        leaves = list(tries[source][package].leaf_paths())
        if not leaves:
            raise ValueError('Empty package trie')
        for leaf in leaves:
            if Path(leaf).is_absolute() or '..' in Path(leaf).parts:
                raise ValueError('Unsafe object-package leaf')
            owned(destination / leaf)
        rows.append({'source': source, 'version': VERSIONS[source], 'package': package,
                     'referenced_files': files, 'leaf_paths': leaves, 'compressed_mb_hint': sizes[source][package],
                     'missing_references': [name for name in files if not (destination / name).is_file()],
                     'missing_leaf_count': sum(not (destination / name).is_file() for name in leaves)})
    plan = {'cohort_sha256': args.cohort_sha256, 'houses': list(houses), 'versions': VERSIONS,
            'first_failure_uid_in_current_index': f'objaverse_{FIRST_UID}.tar.zst' in sizes['objaverse'],
            'reference_counts': {source: len(files) for source, files in references.items()},
            'unresolved_references': unresolved, 'nonobject_missing_references': other_missing,
            'selected_package_count': len(rows), 'packages': rows,
            'scope': 'exact frozen scene XML file dependencies only; current index coverage is not simulator compatibility proof'}
    print(json.dumps(plan, indent=2), flush=True)
    if unresolved:
        raise ValueError('Current-version index cannot supply exact references; preserve evidence and stop')
    if not args.execute:
        return
    if sys.platform != 'linux' or Path(__file__).resolve() != ROOT / 'control/prepare-placement-objects.py' or os.getuid() != 1006 or not os.environ.get('INVOCATION_ID'):
        raise ValueError('Execute only as deploy through task start-job.sh')
    import requests
    class Storage(R2RemoteStorage):
        def __init__(self, source, package):
            super().__init__('mujoco-thor-resources')
            self.source, self.package, self.gets = source, package, 0
            self.http = requests.Session(); self.http.trust_env = False
        def fetch_file(self, *args, **kwargs):
            raise RuntimeError('Unexpected metadata download denied')
        def stream_archive(self, relative, package):
            if str(relative) != f'objects/{self.source}/{VERSIONS[self.source]}' or package != self.package or self.gets >= 1:
                raise ValueError('Only one selected-object GET per isolated attempt')
            self.gets += 1
            response = self.http.get(f'{self.base_url}/{relative}/{package}', stream=True, timeout=(15, 90))
            response.raise_for_status()
            return response.raw
    archive = ROOT / 'state/archive' / ('placement-objects-' + uuid.uuid4().hex[:10])
    archive.mkdir(parents=True)
    (archive / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    results = []
    def guard():
        subprocess.run([sys.executable, str(ROOT / 'control/guard.py'), 'check'], check=True, timeout=15)
    for row in rows:
        guard()
        source, package = row['source'], row['package']
        destination = CACHE / 'objects' / source / VERSIONS[source]
        paths = [destination / leaf for leaf in row['leaf_paths']]
        if any(path.exists() and (not path.is_file() or path.stat().st_size == 0) for path in paths):
            raise ValueError('Ambiguous existing object leaf; preserve for explicit review')
        flag = destination / ('.' + package.replace('/', '__') + '_complete_extract')
        if flag.exists() and any(not path.exists() for path in paths):
            metadata = {'path': str(flag), 'size': flag.stat().st_size, 'mtime_ns': flag.stat().st_mtime_ns,
                        'sha256': hashlib.sha256(flag.read_bytes()).hexdigest()}
            (archive / (source + '-' + package + '.marker.json')).write_text(json.dumps(metadata))
            flag.rename(archive / (source + '-' + flag.name))
        if all(path.is_file() for path in paths) and flag.is_file():
            results.append({'source': source, 'package': package, 'status': 'already_present', 'GETs': 0})
        else:
            policy = json.loads((ROOT / 'control/policy.json').read_text())
            if shutil.disk_usage(ROOT).free < policy['min_disk_free_bytes'] + int(row['compressed_mb_hint'] * 1024 * 1024 * 6):
                raise ValueError('Insufficient disk reserve plus conservative package-size hint')
            passed = False
            for attempt in range(3):
                guard()
                context = mp.get_context('fork')
                parent, child = context.Pipe(duplex=False)
                def install():
                    storage = Storage(source, package)
                    try:
                        manager = ResourceManager(storage, {'objects': {source: VERSIONS[source]}}, ASSETS, CACHE, force_install=False)
                        manager.install_packages('objects', {source: [package]})
                        child.send({'passed': True, 'GETs': storage.gets})
                    except BaseException as error:
                        child.send({'passed': False, 'GETs': storage.gets, 'error_type': type(error).__name__})
                    finally:
                        storage.http.close(); child.close()
                process = context.Process(target=install); process.start(); child.close()
                process.join(timeout=900)
                if process.is_alive():
                    process.terminate(); process.join(timeout=5)
                    if process.is_alive(): process.kill(); process.join(timeout=5)
                    raise TimeoutError('Object attempt exceeded 15 minutes')
                outcome = parent.recv() if parent.poll() else {'passed': False, 'error_type': 'MissingWorkerResult'}
                parent.close()
                if outcome['passed']:
                    passed = True; break
                time.sleep(2)
            if not passed or any(not path.is_file() or path.stat().st_size == 0 for path in paths) or not flag.is_file():
                raise RuntimeError('Selected object package incomplete after bounded retries')
            results.append({'source': source, 'package': package, 'status': 'prepared', 'attempts': attempt + 1})
        (archive / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        guard()


if __name__ == '__main__':
    main()
