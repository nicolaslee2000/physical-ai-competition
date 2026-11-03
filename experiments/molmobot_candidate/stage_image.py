"""Create an allowlisted, task-local build context from verified artifacts."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import urllib.request
import uuid

from .serve import ROOT, PINS, verify_artifacts, owned


def main():
    stage = ROOT / 'packaging/molmobot'
    manifest = json.loads((stage / 'runtime-manifest.json').read_text())
    assert manifest['stage'] == 'resolved_and_imported'
    lock = stage / 'requirements.lock'
    assert hashlib.sha256(lock.read_bytes()).hexdigest() == manifest['lock_sha256']
    probe = json.loads((stage / 'probe/result.json').read_text())
    assert probe['status'] == 'single_process_passed' and len(probe['calls']) == 12
    pins = json.loads(PINS.read_text())
    verify_artifacts(ROOT / 'artifacts/molmobot', pins)
    total = sum(row['size'] for row in pins['artifacts']) + sum(row['bytes'] for row in manifest['wheels'])
    reserve = json.loads((ROOT / 'control/policy.json').read_text())['min_disk_free_bytes']
    assert shutil.disk_usage(ROOT).free > reserve + 3 * total, 'Insufficient build expansion reserve'
    notices = stage / 'notices/public-artifacts'
    notices.mkdir(exist_ok=True)
    urls = {
        'MolmoBot-DROID-card.md': f'https://huggingface.co/allenai/MolmoBot-DROID/resolve/{pins["weights_revision"]}/README.md',
        'Qwen-tokenizer-card.md': f'https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/resolve/{pins["tokenizer"]["revision"]}/README.md',
        'Qwen-tokenizer-LICENSE': f'https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/resolve/{pins["tokenizer"]["revision"]}/LICENSE',
    }
    for name, url in urls.items():
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read(2_000_001)
        assert 0 < len(data) <= 2_000_000
        (notices / name).write_bytes(data)
    run_id = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    context = owned(stage / ('image-context-' + run_id))
    context.mkdir()
    rows = []
    def stage_file(source, relative, *, link=False, expected=None):
        source = owned(source)
        assert source.is_file() and not source.is_symlink(), f'Missing regular input: {source}'
        destination = context / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if expected:
            assert source.stat().st_size == expected['bytes']
            assert hashlib.sha256(source.read_bytes()).hexdigest() == expected['sha256']
        (os.link if link else shutil.copyfile)(source, destination)
        rows.append({'path': str(relative), 'bytes': destination.stat().st_size})
    package = ROOT / 'experiments/molmobot_candidate'
    for name in ('Dockerfile', '.dockerignore'):
        stage_file(package / name, name)
    stage_file(lock, 'requirements.lock')
    for row in manifest['wheels']:
        stage_file(stage / 'wheelhouse' / row['file'], Path('wheelhouse') / row['file'], link=True, expected=row)
    for name in ('__init__.py','adapter.py','native.py','serve.py','packaging-pins.json'):
        stage_file(package / name, Path('molmobot_candidate') / name)
    for row in pins['artifacts']:
        stage_file(ROOT / 'artifacts/molmobot' / row['path'], Path('artifacts') / row['path'], link=True)
    for source in (stage / 'notices').rglob('*'):
        if source.is_file():
            stage_file(source, Path('notices') / source.relative_to(stage / 'notices'))
    record = {'run_id': run_id, 'context': str(context), 'files': rows,
              'source_manifest': str(stage / 'source-manifest.json'),
              'requirements_sha256': manifest['lock_sha256'],
              'dockerfile_sha256': hashlib.sha256((context / 'Dockerfile').read_bytes()).hexdigest(),
              'public_notice_urls': urls, 'no_official_submission': True}
    (stage / 'image-build-plan.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'context': str(context), 'files':len(rows), 'logical_bytes':sum(r['bytes'] for r in rows)}))


if __name__ == '__main__':
    main()
