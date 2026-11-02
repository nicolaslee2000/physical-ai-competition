#!/usr/bin/env python3
"""Probe a hardware EGL context on the selected simulator device, without a policy."""
import pathlib
import subprocess
import sys
import argparse

root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'experiments'))
from local_eval import environment, namespace_command

parser = argparse.ArgumentParser()
parser.add_argument('--device', type=int, default=0)
args = parser.parse_args()
env = environment()
env['CUDA_VISIBLE_DEVICES'] = '1'
env['MUJOCO_EGL_DEVICE_ID'] = str(args.device)
env.pop('LIBGL_ALWAYS_SOFTWARE', None)
command = namespace_command([str(root / 'cache/positronic/molmospaces/src/.venv/bin/python'), '-c',
    'import mujoco; ctx=mujoco.GLContext(64,64); ctx.make_current(); from OpenGL.GL import glGetString,GL_VENDOR,GL_RENDERER; print(glGetString(GL_VENDOR)); print(glGetString(GL_RENDERER)); ctx.free()'])
subprocess.run(command, env=env, cwd=root, timeout=30, check=True)
