#!/usr/bin/env python3
"""Immediately mirror one live credential-free usage snapshot, without rearming jobs."""
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
REMOTE = '/opt/hderc-internal/nick/physical-ai-competition/state/usage.json'


def validated(snapshot, now):
    collected = snapshot.get('collected_at')
    remaining = snapshot.get('remaining_percent')
    if type(collected) not in (int, float) or not math.isfinite(collected) or not -30 <= now - collected <= 60:
        raise ValueError('Require a live snapshot collected within the last minute')
    if not isinstance(remaining, list) or not remaining or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 100 for v in remaining):
        raise ValueError('Missing or invalid usage windows')
    return {'collected_at': collected, 'remaining_percent': remaining}


def main():
    snapshot = validated(json.load(sys.stdin), time.time())
    path = ROOT / 'state/usage.json'
    path.parent.mkdir(exist_ok=True)
    temporary = path.with_suffix('.json.new')
    temporary.write_text(json.dumps(snapshot) + '\n')
    temporary.replace(path)
    subprocess.run(['scp', '-q', str(path), f'hdhyundai-deploy:{REMOTE}.new'], check=True, timeout=25)
    subprocess.run(['ssh', 'hdhyundai-deploy', f'mv -- {REMOTE}.new {REMOTE}'], check=True, timeout=25)
    print(json.dumps({'mirrored': True, **snapshot}))
    # This helper deliberately never clears STOP/stopped.json or starts services.


if __name__ == '__main__':
    main()
