#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
python3 "$task_root/control/guard.py" check
cd "$task_root"
mkdir -p bin tmp cache/uv data/uv/python models/molmospaces/assets cache/molmospaces
export TMPDIR="$task_root/tmp" UV_CACHE_DIR="$task_root/cache/uv"
export UV_PYTHON_INSTALL_DIR="$task_root/data/uv/python"
export PHYSICAL_AI_CACHE_DIR="$task_root/cache/positronic"
export MLSPACES_ASSETS_DIR="$task_root/models/molmospaces/assets"
export MLSPACES_CACHE_DIR="$task_root/cache/molmospaces"
if [ ! -x "$task_root/bin/uv" ]; then
  curl -fsSL https://astral.sh/uv/install.sh -o "$task_root/tmp/install-uv.sh"
  UV_INSTALL_DIR="$task_root/bin" UV_NO_MODIFY_PATH=1 sh "$task_root/tmp/install-uv.sh"
fi
export PATH="$task_root/bin:$PATH"
if [ ! -d "$task_root/positronic/.git" ]; then
  git clone https://github.com/Positronic-Robotics/positronic "$task_root/positronic"
  git -C "$task_root/positronic" checkout --detach 00fdd933f22158a9cbe6d97c5b19c2935df35c1b
fi
python3 "$task_root/experiments/prepare_cache_patch.py"
uv sync --project "$task_root/positronic" --locked --managed-python --python 3.13 --no-dev --extra telemetry
python3 "$task_root/control/guard.py" check
# Prepare the pinned simulator environment under the patched task cache path.
"$task_root/positronic/.venv/bin/python" -c 'from positronic.simulator.molmo_spaces.launcher import ensure_molmo_venv; print(ensure_molmo_venv())'
printf '%s\n' 'Local evaluator dependencies prepared; live smoke evaluation is next.'
