#!/usr/bin/env python3
"""Prepare simulator resource metadata without allocating policy GPU memory."""
import pathlib
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'experiments'))
from local_eval import environment, namespace_command

subprocess.run([sys.executable, str(root / 'control/guard.py'), 'check'], check=True)
python = root / 'cache/positronic/molmospaces/src/.venv/bin/python'
command = namespace_command([str(python), '-c',
    'from molmo_spaces.molmo_spaces_constants import get_resource_manager; get_resource_manager(); print("Simulator resource metadata prepared")'])
with (root / 'logs/assets.log').open('a') as log:
    subprocess.run(command, env=environment(), cwd=root, stdout=log, stderr=subprocess.STDOUT, timeout=1200, check=True)
