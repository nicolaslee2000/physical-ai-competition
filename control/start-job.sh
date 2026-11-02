#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
python3 "$task_root/control/guard.py" check
user_runtime="/run/user/$(id -u)"
if XDG_RUNTIME_DIR="$user_runtime" systemctl --user is-active --quiet nick-physical-ai-eval; then
  echo 'A task GPU job is already active.' >&2
  exit 2
fi
cd "$task_root"
cpu_list=$(python3 -c 'import os; print(",".join(map(str, sorted(os.sched_getaffinity(0))[:4])))')
XDG_RUNTIME_DIR="$user_runtime" systemd-run --user --unit=nick-physical-ai-eval --collect \
  --property=MemoryMax=28G --property=MemorySwapMax=0 --property=TimeoutStopSec=15s \
  --property=KillMode=control-group \
  --property="WorkingDirectory=$task_root" \
  --property="StandardOutput=append:$task_root/logs/job.log" \
  --property="StandardError=append:$task_root/logs/job.log" \
  /usr/bin/taskset --cpu-list "$cpu_list" /usr/bin/env \
  "TMPDIR=$task_root/tmp" "XDG_CACHE_HOME=$task_root/cache" \
  "HF_HOME=$task_root/cache/huggingface" "UV_CACHE_DIR=$task_root/cache/uv" \
  "XDG_CONFIG_HOME=$task_root/config" "XDG_DATA_HOME=$task_root/data" \
  "UV_PYTHON_INSTALL_DIR=$task_root/data/uv/python" "TORCH_HOME=$task_root/cache/torch" \
  "CUDA_CACHE_PATH=$task_root/cache/cuda" "WANDB_DIR=$task_root/logs" \
  "DOCKER_HOST=unix://$task_root/runtime/docker.sock" "DOCKER_CONFIG=$task_root/config/docker" \
  "$@"
