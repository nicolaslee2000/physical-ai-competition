#!/usr/bin/env python3
"""Acquire six pinned public artifacts inside the task root; no model is loaded."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path('/opt/hderc-internal/nick/physical-ai-competition')


def guard():
    subprocess.run([sys.executable, str(ROOT / 'control/guard.py'), 'check'],
                   check=True, capture_output=True, timeout=15)


def checked_path(path):
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError('Path outside task root')
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError('Symlink in acquisition path')
        if parent == ROOT:
            break
    return path


def digest_match(row, sha256, git_sha):
    return (('sha256' not in row or sha256 == row['sha256']) and
            ('git_blob_sha1' not in row or git_sha == row['git_blob_sha1']))


def acquire(row, url, directory):
    relative = Path(row['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Invalid artifact path')
    target = checked_path(directory / relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256()
    git_sha = hashlib.sha1(f'blob {row["size"]}\0'.encode())
    size = 0
    if target.exists():
        with target.open('rb') as stream:
            for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                size += len(chunk); sha.update(chunk); git_sha.update(chunk)
        if size != row['size'] or not digest_match(row, sha.hexdigest(), git_sha.hexdigest()):
            raise ValueError('Existing artifact differs; preserve for review')
        return {'path': row['path'], 'status': 'already_verified', 'bytes': size}
    minimum = json.loads((ROOT / 'control/policy.json').read_text())['min_disk_free_bytes']
    if shutil.disk_usage(ROOT).free < minimum + row['size']:
        raise ValueError('Insufficient disk reserve for artifact')
    temporary = checked_path(ROOT / 'tmp' / ('molmobot-download-' + uuid.uuid4().hex))
    last_guard = last_progress = time.monotonic()
    # No Hub library, user cache, credentials, auth headers or external output paths.
    request = urllib.request.Request(url, headers={'User-Agent': 'Nick-Physical-AI-public-artifacts/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open('xb') as output:
            if response.status != 200:
                raise ValueError('Expected whole immutable artifact')
            for chunk in iter(lambda: response.read(4 * 1024 * 1024), b''):
                size += len(chunk)
                if size > row['size']:
                    raise ValueError('Artifact exceeds pinned size')
                output.write(chunk); sha.update(chunk); git_sha.update(chunk)
                now = time.monotonic()
                if now - last_guard >= 15:
                    guard(); last_guard = now
                if now - last_progress >= 30:
                    print(json.dumps({'path': row['path'], 'bytes_received': size}), flush=True)
                    last_progress = now
            output.flush(); os.fsync(output.fileno())
        if size != row['size'] or not digest_match(row, sha.hexdigest(), git_sha.hexdigest()):
            raise ValueError('Pinned artifact size/hash mismatch')
        if target.exists() or target.is_symlink():
            raise ValueError('Artifact destination appeared during acquisition')
        os.rename(temporary, target)
        return {'path': row['path'], 'status': 'downloaded_verified', 'bytes': size}
    except BaseException:
        # Keep partial bytes under task tmp for diagnosis; never overwrite a prior artifact.
        print(json.dumps({'path': row['path'], 'partial_file': str(temporary), 'bytes_received': size}), flush=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if Path(__file__).resolve().parent != ROOT / 'control' or os.getuid() != 1006:
        raise ValueError('Use isolated deploy checkout')
    pins = json.loads(checked_path(ROOT / 'experiments/molmobot_candidate/packaging-pins.json').read_text())
    directory = checked_path(ROOT / 'artifacts/molmobot')
    print(json.dumps({'artifacts': len(pins['artifacts']), 'total_bytes': sum(x['size'] for x in pins['artifacts']),
                      'directory': str(directory), 'model_or_gpu_loaded': False}), flush=True)
    if not args.execute:
        return
    invocation = subprocess.check_output(['systemctl', '--user', 'show', 'nick-physical-ai-eval.service',
                                          '--property=InvocationID', '--value'], text=True).strip()
    if not invocation or invocation != os.environ.get('INVOCATION_ID'):
        raise ValueError('Launch only through control/start-job.sh')
    guard()
    rows = []
    for row in pins['artifacts']:
        guard()
        prefix, filename = row['path'].split('/', 1)
        if prefix == 'checkpoint' and filename in ('model.pt', 'config.yaml'):
            repo, revision = 'allenai/MolmoBot-DROID', pins['weights_revision']
        elif prefix == 'tokenizer' and filename in ('merges.txt', 'tokenizer.json', 'tokenizer_config.json', 'vocab.json'):
            repo, revision = pins['tokenizer']['repo'], pins['tokenizer']['revision']
        else:
            raise ValueError('Unreviewed artifact')
        rows.append(acquire(row, f'https://huggingface.co/{repo}/resolve/{revision}/{filename}?download=true', directory))
        print(json.dumps(rows[-1]), flush=True)
    report = ROOT / 'state/molmobot-artifact-acquisition.json'
    report.write_text(json.dumps({'status': 'verified_downloads_only', 'at_unix': time.time(), 'files': rows}, indent=2) + '\n')
    guard()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}), file=sys.stderr)
        raise SystemExit(2)
