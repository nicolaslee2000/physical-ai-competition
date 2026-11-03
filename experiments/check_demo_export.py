#!/usr/bin/env python3
"""Source-hash and official GR00T export qualification; never trains or claims gains."""
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path('/opt/hderc-internal/nick/physical-ai-competition')
MANIFEST_SHA = '9c6b661c4c8c75517fcb651f66dc4df7820f88584265759d12fa7a6ad941630e'
DIMS = {'eef_9d': 9, 'gripper_position': 1, 'joint_position': 7}


def owned(path, root=ROOT):
    path = Path(path)
    if not path.is_absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path must stay inside the isolated task root')
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError('Symlink in source/export path')
        if parent == root:
            break
    return path


def verify_source(source, manifest_path, digest=MANIFEST_SHA, root=ROOT):
    source, manifest_path = owned(source, root), owned(manifest_path, root)
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Source manifest SHA mismatch')
    manifest = json.loads(raw)
    objects = manifest['objects']
    if len(objects) != 170:
        raise ValueError('Require all 170 audited source objects')
    listed = set()
    for row in objects:
        relative = row['relative_path']
        parts = relative.split('/')
        if len(parts) != 3 or any(part in ('', '.', '..') for part in parts) or '\\' in relative or relative.startswith('/'):
            raise ValueError('Invalid manifest object path')
        path = owned(source / relative, root)
        if relative in listed or not path.is_file():
            raise ValueError('Missing/duplicate source object')
        listed.add(relative)
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(chunk)
        if path.stat().st_size != row['bytes'] or h.hexdigest() != row['sha256']:
            raise ValueError('Source object size/hash mismatch')
    actual = set()
    for path in source.rglob('*'):
        owned(path, root)
        if path.is_file():
            actual.add(str(path.relative_to(source)))
    if actual != listed:
        raise ValueError('Source dataset contains unaudited files')
    return {'source_objects_verified': len(objects), 'source_manifest_sha256': digest}


def check_metadata(info, modality, episodes):
    if info.get('fps') != 15 or info.get('total_episodes') != 10 or not info.get('total_frames', 0) > 0:
        raise ValueError('Expected ten episodes, positive frames, and recipe 15 fps')
    if len(episodes) != 10 or {row['episode_index'] for row in episodes} != set(range(10)) or any(row.get('length', 0) <= 0 for row in episodes):
        raise ValueError('Missing/empty/duplicate exported episode')
    if sum(row['length'] for row in episodes) != info['total_frames']:
        raise ValueError('Episode/frame totals disagree')
    features = info['features']
    if features['action']['shape'] != [17]:
        raise ValueError('Expected 17D actions')
    position = 0
    for name, dimension in DIMS.items():
        state, action = modality['state'][name], modality['action'][name]
        if features[name]['shape'] != [dimension] or (state['start'], state['end']) != (0, dimension):
            raise ValueError('State feature/modality dimensions disagree')
        if (action['start'], action['end']) != (position, position + dimension):
            raise ValueError('Action modality slices disagree')
        position += dimension
    if not modality.get('video') or not modality.get('annotation'):
        raise ValueError('Missing video/task modality')
    return info['total_frames']


def finite_action(action):
    if not isinstance(action, (list, tuple)) or len(action) != 17 or any(type(value) not in (float, int) or not math.isfinite(value) for value in action):
        raise ValueError('Expected finite 17D action row')


def verify_export(path):
    path = owned(path)
    info = json.loads((path / 'meta/info.json').read_text())
    modality = json.loads((path / 'meta/modality.json').read_text())
    episodes = [json.loads(line) for line in (path / 'meta/episodes.jsonl').read_text().splitlines() if line.strip()]
    total = check_metadata(info, modality, episodes)
    import pyarrow.parquet as pq
    count, indices = 0, set()
    for shard in sorted((path / 'data').rglob('*.parquet')):
        owned(shard)
        for batch in pq.ParquetFile(shard).iter_batches(columns=['action', 'episode_index'], batch_size=1024):
            columns = batch.to_pydict()
            for action, index in zip(columns['action'], columns['episode_index']):
                finite_action(action)
                count += 1
                indices.add(index)
    if count != total or indices != set(range(10)):
        raise ValueError('Parquet action coverage differs from metadata')
    return {'export_verified': True, 'episodes': 10, 'frames': total, 'fps': 15, 'action_dimensions': 17,
            'finite_action_rows': count, 'scope': 'conversion/schema qualification only; no training or measured policy gain'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    source = commands.add_parser('source')
    source.add_argument('--dataset', type=Path, required=True)
    source.add_argument('--manifest', type=Path, required=True)
    export = commands.add_parser('export')
    export.add_argument('--dataset', type=Path, required=True)
    args = parser.parse_args()
    result = verify_source(args.dataset, args.manifest) if args.mode == 'source' else verify_export(args.dataset)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
