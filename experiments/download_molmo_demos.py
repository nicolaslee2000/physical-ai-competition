#!/usr/bin/env python3
"""Mac-only, unsigned, bounded public ten-demo pilot. No model/GPU/conversion work."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'datasets/molmo-pick-demos/v1/'
ENDPOINT = 'https://storage.eu-north1.nebius.cloud'
MAX_BYTES = 100 * 1024 * 1024


def safe_target(destination, key):
    if not key.startswith(PREFIX) or '\\' in key:
        raise ValueError('Wrong public dataset or unsafe object path')
    relative = key[len(PREFIX):]
    parts = relative.split('/')
    if len(parts) != 3 or any(part in ('', '.', '..') for part in parts) or not all(part.isdecimal() for part in parts[:2]):
        raise ValueError('Unsafe episode object path')
    target = destination.joinpath(*parts)
    for parent in (destination, *target.parents):
        if parent.is_symlink():
            raise ValueError('Symlink in target ancestry')
        if parent == ROOT:
            break
    if target.is_symlink() or not target.resolve().is_relative_to(destination.resolve()):
        raise ValueError('Target escapes dataset directory')
    return target


def stream_object(body, target, expected_size, remaining, expected_sha=None):
    if expected_size < 0 or expected_size > remaining:
        raise ValueError('Object exceeds remaining byte budget')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.partial-' + uuid.uuid4().hex)
    digest, size = hashlib.sha256(), 0
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            while chunk := body.read(min(1024 * 1024, expected_size - size + 1)):
                size += len(chunk)
                if size > expected_size or size > remaining:
                    raise ValueError('Stream exceeds advertised size or byte budget')
                digest.update(chunk)
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        actual = digest.hexdigest()
        if size != expected_size or expected_sha is not None and actual != expected_sha:
            raise ValueError('Object size or audited static SHA changed')
        if target.is_symlink():
            raise ValueError('Target became a symlink')
        temporary.replace(target)
        return actual, size
    finally:
        body.close()
        if temporary.exists():
            temporary.unlink()


def audited_objects():
    audit = json.loads((ROOT / 'state/public-data/metadata-audit.json').read_text())
    episodes = audit['sources']['molmo_pick_demos']['episodes']
    if len(episodes) != 10 or any(row['metadata'].get('eval.success') is not True for row in episodes):
        raise ValueError('Require ten audited successful demonstrations')
    expected, identities = {}, set()
    for row in episodes:
        directory, metadata = row['source_directory'], row['metadata']
        identity = '/'.join(str(metadata[key]) for key in ('molmo.suite', 'molmo.scene_dataset', 'molmo.task_config', 'molmo.benchmark', 'molmo.episode_index'))
        identities.add(identity)
        expected[directory + '/static.json'] = row['static_json_sha256']
        for filename in row['signal_object_names']:
            if PurePosixPath(filename).name != filename:
                raise ValueError('Invalid audited filename')
            expected[directory + '/' + filename] = None
    if len(identities) != 10:
        raise ValueError('Duplicate demonstration identities')
    for name in ('fresh-pick-cohort.json', 'fresh-placement-cohort.json'):
        frozen = json.loads((ROOT / 'experiments' / name).read_text())
        if identities & {row['episode_path'] for row in frozen['episodes']}:
            raise ValueError('Demonstration overlaps frozen validation')
    return expected


def validate_reader(destination):
    import numpy as np
    from positronic.dataset.local_dataset import LocalDataset
    dataset = LocalDataset(destination)
    if len(dataset) != 10:
        raise ValueError('Expected ten readable episodes')
    records = []
    for episode in dataset:
        static = episode.static
        if static.get('eval.success') is not True or static.get('eval.embodiment') != 'remote.molmo_spaces.droid':
            raise ValueError('Downloaded episode success/embodiment mismatch')
        names = ('robot_state.q', 'robot_state.ee_pose', 'target_grip', 'image.exterior', 'image.exterior_2', 'image.wrist')
        metadata = {name: episode[name].meta for name in names}
        if metadata['robot_state.q'].shape != (7,) or metadata['robot_state.ee_pose'].shape != (7,) or metadata['target_grip'].shape != ():
            raise ValueError('Unexpected state/action dimensions')
        for camera in ('image.exterior', 'image.exterior_2', 'image.wrist'):
            if len(metadata[camera].shape) != 3 or metadata[camera].shape[-1] != 3 or np.dtype(metadata[camera].dtype) != np.dtype('uint8'):
                raise ValueError('Expected RGB uint8 camera schema')
        records.append({'index': static['molmo.episode_index'], 'signals': {name: str(episode[name].meta) for name in names}})
    return {'status': 'ten_episodes_and_signal_metadata_readable', 'episodes': records,
            'limitation': 'Reader/schema check only; conversion and training have not run.'}


def main():
    if sys.platform != 'darwin':
        raise ValueError('This pilot is authorized only on the Mac')
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
    expected = audited_objects()
    destination = ROOT / 'state/public-data/molmo_pick_demos'
    for key in expected:
        safe_target(destination, key)
    client = boto3.client('s3', endpoint_url=ENDPOINT, region_name='eu-north1', aws_access_key_id='', aws_secret_access_key='',
                          config=Config(signature_version=UNSIGNED, connect_timeout=5, read_timeout=15, retries={'total_max_attempts': 1}))
    listing = client.list_objects_v2(Bucket='positronic-public', Prefix=PREFIX, MaxKeys=1000)
    objects = [row for row in listing.get('Contents', []) if not row['Key'].endswith('/')]
    if listing.get('IsTruncated') or {row['Key'] for row in objects} != set(expected):
        raise ValueError('Public object listing changed from audit or exceeds one bounded page')
    if len(objects) > 200 or sum(row['Size'] for row in objects) > MAX_BYTES:
        raise ValueError('Dataset exceeds 200 GET / 100 MiB pilot budget')
    manifest = {'source': 's3://PUBLIC@positronic-public/' + PREFIX, 'endpoint': ENDPOINT,
                'attribution': 'Positronic public MolmoSpaces human pick mini demonstrations',
                'license_note': 'No standalone data license found; public access and software Apache-2.0 are not a redistribution grant.',
                'frozen_validation_fullpath_overlap': False, 'objects': []}
    total = 0
    for row in sorted(objects, key=lambda value: value['Key']):
        target = safe_target(destination, row['Key'])
        response = client.get_object(Bucket='positronic-public', Key=row['Key'])
        if response['ContentLength'] != row['Size']:
            response['Body'].close()
            raise ValueError('Object changed since bounded listing')
        digest, count = stream_object(response['Body'], target, row['Size'], MAX_BYTES - total, expected[row['Key']])
        total += count
        manifest['objects'].append({'source_key': row['Key'], 'relative_path': str(target.relative_to(destination)), 'bytes': count, 'sha256': digest})
    manifest.update(bytes_downloaded=total, get_requests=len(objects), list_requests=1)
    try:
        manifest['reader_validation'] = validate_reader(destination)
    except (ImportError, ModuleNotFoundError) as exc:
        manifest['reader_validation'] = {'status': 'files_ready_reader_dependency_missing', 'missing_module': getattr(exc, 'name', None), 'error_type': type(exc).__name__}
    output = destination.parent / 'molmo_pick_demos-download-manifest.json'
    raw = (json.dumps(manifest, indent=2) + '\n').encode()
    temporary = output.with_suffix('.json.new')
    temporary.write_bytes(raw)
    temporary.replace(output)
    print(json.dumps({'objects': len(objects), 'bytes': total, 'GETs': len(objects), 'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'reader_status': manifest['reader_validation']['status']}))


if __name__ == '__main__':
    main()
