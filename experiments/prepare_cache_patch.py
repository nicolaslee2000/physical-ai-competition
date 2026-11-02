#!/usr/bin/env python3
"""Apply two exact, fail-closed task-cache redirects to an editable upstream checkout."""
import argparse
from pathlib import Path

ROOT = Path('/opt/hderc-internal/nick/physical-ai-competition')
PATCHES = {
    'positronic/simulator/molmo_spaces/launcher.py': (
        "_MOLMO_SRC = Path.home() / '.cache' / 'positronic' / 'molmospaces' / 'src'",
        "_MOLMO_SRC = Path(__import__('os').environ['PHYSICAL_AI_CACHE_DIR']) / 'molmospaces' / 'src'"),
    'positronic/simulator/env_server/launcher.py': (
        "_PORT_LOCKS = Path.home() / '.cache' / 'positronic' / 'env_server_ports'",
        "_PORT_LOCKS = Path(os.environ['PHYSICAL_AI_CACHE_DIR']) / 'env_server_ports'"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT / 'positronic')
    args = parser.parse_args()
    if not args.repo.resolve().is_relative_to(ROOT):
        raise ValueError('Only the isolated server checkout may be patched')
    changes = []
    for name, (before, after) in PATCHES.items():
        path = args.repo / name
        text = path.read_text()
        if after in text:
            continue
        if text.count(before) != 1:
            raise ValueError(f'Upstream changed: review {path}')
        changes.append((path, text.replace(before, after)))
    for path, text in changes:
        path.write_text(text)
    print('Task cache redirects prepared; install this checkout editable before evaluation.')


if __name__ == '__main__':
    main()
