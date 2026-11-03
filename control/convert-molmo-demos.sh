#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
[[ "$task_root" == /opt/hderc-internal/nick/physical-ai-competition ]] || { echo 'Use the isolated server checkout.' >&2; exit 2; }
# Caller must use start-job.sh; do not execute a second conversion alongside evaluation.
[[ "${INVOCATION_ID:-}" != '' ]] || { echo 'Launch through control/start-job.sh.' >&2; exit 2; }
python3 "$task_root/control/guard.py" check
python3 "$task_root/experiments/check_demo_export.py" source \
  --dataset "$task_root/data/molmo_pick_demos" \
  --manifest "$task_root/data/molmo_pick_demos-download-manifest.json"
export UV_PROJECT_ENVIRONMENT="$task_root/conversion/.venv"
export UV_CACHE_DIR="$task_root/cache/uv-conversion"
export UV_PYTHON_INSTALL_DIR="$task_root/data/uv/python"
export TMPDIR="$task_root/tmp"
export XDG_CACHE_HOME="$task_root/cache/conversion"
export XDG_CONFIG_HOME="$task_root/config/conversion"
export XDG_DATA_HOME="$task_root/data/conversion"
export HF_HOME="$task_root/cache/huggingface-conversion"
export TORCH_HOME="$task_root/cache/torch-conversion"
export CUDA_CACHE_PATH="$task_root/cache/cuda-conversion"
export NUMBA_CACHE_DIR="$task_root/cache/numba-conversion"
export JAX_COMPILATION_CACHE_DIR="$task_root/cache/jax-conversion"
export WANDB_DIR="$task_root/logs/conversion"
export CUDA_VISIBLE_DEVICES=''
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
# Refuse cache/env paths that resolve outside the task root, including symlink ancestors.
python3 - "$task_root" <<'PY'
import os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(sys.argv[1]) / 'experiments'))
from check_demo_export import owned
owned(pathlib.Path(sys.argv[1]) / 'conversion/datasets')
for key in ('UV_PROJECT_ENVIRONMENT','UV_CACHE_DIR','UV_PYTHON_INSTALL_DIR','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','HF_HOME','TORCH_HOME','CUDA_CACHE_PATH','NUMBA_CACHE_DIR','JAX_COMPILATION_CACHE_DIR','WANDB_DIR'):
    owned(pathlib.Path(os.environ[key]))
PY
mkdir -p "$task_root/conversion/datasets" "$TMPDIR" "$WANDB_DIR"
run_id=$(python3 -c 'import datetime,uuid;print(datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:8])')
output="$task_root/conversion/datasets/pilot-run-$run_id"
[[ ! -e "$output" && ! -L "$output" ]] || exit 2
python3 "$task_root/control/guard.py" check
/usr/bin/timeout --kill-after=30s 30m "$task_root/bin/uv" sync \
  --project "$task_root/positronic" --locked --managed-python --python 3.13 --extra lerobot_0_3_3 --no-dev
[[ "$(readlink -f "$UV_PROJECT_ENVIRONMENT/bin/python")" == "$task_root/"* ]] || exit 2
python3 "$task_root/control/guard.py" check
# Direct isolated-env Python avoids uv resyncing the active evaluator environment.
/usr/bin/timeout --kill-after=30s 15m "$UV_PROJECT_ENVIRONMENT/bin/python" \
  -m positronic.vendors.lerobot_0_3_3.to_lerobot convert \
  --dataset=@positronic.cfg.ds.transform \
  --dataset.base=@positronic.cfg.ds.local \
  --dataset.base.path="$task_root/data/molmo_pick_demos" \
  '--dataset.transforms=["@positronic.vendors.gr00t.recipes.droid_molmo"]' \
  --num_workers=2 --output_dir="$output"
python3 "$task_root/control/guard.py" check
"$UV_PROJECT_ENVIRONMENT/bin/python" "$task_root/experiments/check_demo_export.py" export --dataset "$output" \
  > "$task_root/conversion/export-check-$run_id.json"
python3 "$task_root/control/guard.py" check
printf '%s\n' "$output"
