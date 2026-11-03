#!/usr/bin/env python3
"""Unsigned S3 metadata-only audit. Never calls pos3.download or fetches signal/video payloads."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = 'https://storage.eu-north1.nebius.cloud'
PREFIXES = {'molmo_pick_demos': 'datasets/molmo-pick-demos/v1/', 'sim_pick_place': 'datasets/sim-pick-place/'}
SAFE = {'task', 'ee_frames', 'joint_signals', 'pose_signals', 'joint_names', 'gripper', 'eval.embodiment', 'eval.universe', 'eval.success', 'eval.terminated', 'eval.trial_index', 'eval.trial_count', 'molmo.suite', 'molmo.scene_dataset', 'molmo.task_config', 'molmo.benchmark', 'molmo.episode_index', 'molmo.exterior_sides'}


def main():
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
    client = boto3.client('s3', endpoint_url=ENDPOINT, region_name='eu-north1',
                          aws_access_key_id='', aws_secret_access_key='',
                          config=Config(signature_version=UNSIGNED, connect_timeout=5, read_timeout=15, retries={'max_attempts': 1}))
    destination = ROOT / 'state/public-data'
    destination.mkdir(parents=True, exist_ok=True)
    report = {'access': 'anonymous unsigned S3; no profiles/credentials read', 'data_payloads_downloaded': False, 'sources': {}}
    budget = 12 * 1024 * 1024
    for name, prefix in PREFIXES.items():
        objects = []
        for page in client.get_paginator('list_objects_v2').paginate(Bucket='positronic-public', Prefix=prefix):
            objects.extend(page.get('Contents', []))
        statics = sorted((obj for obj in objects if obj['Key'].endswith('/static.json')), key=lambda row: row['Key'])
        selected = statics if name == 'molmo_pick_demos' else statics[:3]
        source = {'s3_url': 's3://PUBLIC@positronic-public/' + prefix,
                  'source_episode_directories': [obj['Key'].rsplit('/', 1)[0] for obj in statics],
                  'listed_episode_count': len(statics), 'listed_bytes': sum(obj['Size'] for obj in objects),
                  'static_metadata_sample_count': len(selected), 'episodes': [],
                  'license_or_attribution_objects': [obj['Key'] for obj in objects if any(word in obj['Key'].rsplit('/', 1)[-1].lower() for word in ('license', 'notice', 'readme', 'attribution'))]}
        for obj in selected:
            if obj['Size'] > budget:
                raise ValueError('Metadata byte budget exhausted; stop without signal downloads')
            key = obj['Key']; directory = key.rsplit('/', 1)[0]
            response = client.get_object(Bucket='positronic-public', Key=key)
            raw = response['Body'].read(budget + 1); budget -= len(raw)
            if budget < 0:
                raise ValueError('Metadata byte budget exhausted')
            data = json.loads(raw)
            entry = {'source_directory': directory, 'static_json_sha256': hashlib.sha256(raw).hexdigest(),
                     'metadata': {key: value for key, value in data.items() if key in SAFE},
                     'signal_object_names': sorted(obj['Key'].rsplit('/', 1)[-1] for obj in objects if obj['Key'].startswith(directory + '/') and not obj['Key'].endswith('/static.json'))}
            source['episodes'].append(entry)
        report['sources'][name] = source
    frozen = {}
    for filename in ('fresh-pick-cohort.json', 'fresh-placement-cohort.json'):
        cohort = json.loads((ROOT / 'experiments' / filename).read_text())
        frozen[filename] = {row['episode_path'] for row in cohort['episodes']}
    demo = report['sources']['molmo_pick_demos']['episodes']
    for filename, paths in frozen.items():
        overlaps = []
        for row in demo:
            data = row['metadata']
            full = '/'.join(str(data[key]) for key in ('molmo.suite', 'molmo.scene_dataset', 'molmo.task_config', 'molmo.benchmark', 'molmo.episode_index'))
            if full in paths:
                overlaps.append(full)
        report.setdefault('full_path_overlap', {})[filename] = overlaps
    report['sim_overlap_status'] = 'Sampled sim metadata has no Molmo benchmark/index IDs; absence of overlap cannot be established from names.'
    report['metadata_bytes_read'] = 12 * 1024 * 1024 - budget
    (destination / 'metadata-audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'metadata_bytes_read': report['metadata_bytes_read'], 'episodes': {name: source['listed_episode_count'] for name, source in report['sources'].items()}, 'overlap': report['full_path_overlap']}))


if __name__ == '__main__':
    main()
