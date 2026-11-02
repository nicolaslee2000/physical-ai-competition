#!/usr/bin/env python3
"""Read campaign instructions each wake; display full text whenever it changes."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
cache = root / 'state/instruction-hashes.json'
known = json.loads(cache.read_text()) if cache.exists() else {}
current = {}
for relative in ('AGENTS.md', 'control/policy.json', 'control/OVERNIGHT.md', 'EXPERIMENTS.md'):
    content = (root / relative).read_text()
    current[relative] = hashlib.sha256(content.encode()).hexdigest()
    print(f'{relative}: unchanged' if known.get(relative) == current[relative] else f'{relative}:\n{content}')
cache.parent.mkdir(exist_ok=True)
temporary = cache.with_suffix('.json.new')
temporary.write_text(json.dumps(current, indent=2) + '\n')
temporary.replace(cache)
