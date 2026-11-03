#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
[[ "$task_root" == /opt/hderc-internal/nick/physical-ai-competition && "$(id -u)" == 1006 ]] || exit 2
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
[[ -n "${INVOCATION_ID:-}" && "$(systemctl --user show nick-physical-ai-eval.service --property=InvocationID --value)" == "$INVOCATION_ID" ]] || exit 2
exec 9>"$task_root/experiments/eval.lock"
flock -n 9 || exit 2
python3 "$task_root/control/guard.py" check
engine=(bash "$task_root/docker/engine.sh")
[[ "$("${engine[@]}" info --format '{{json .SecurityOptions}}')" == *rootless* ]] || exit 2
base='pytorch/pytorch@sha256:417bd75df6365104c283ea4c1651fb3530d9eb5a4c2fafa51943cff2a94e6385'
if ! "${engine[@]}" image inspect "$base" --format '{{.Id}}' >/dev/null 2>&1; then
  /usr/bin/timeout --kill-after=30s 20m "${engine[@]}" pull "$base"
fi
python3 "$task_root/control/guard.py" check
# CPU-only inventory: no model weights, GPU allocation, host mounts or network.
"${engine[@]}" run --rm --pull=never --network=none --memory=3g --memory-swap=3g \
  "$base" python -c 'import sys,torch,json; print(json.dumps({"python":sys.version,"torch":torch.__version__,"cuda_build":torch.version.cuda,"scope":"base package inventory only; no model or GPU test"}))' \
  > "$task_root/state/molmobot-base-inventory.json"
python3 "$task_root/control/guard.py" check
/usr/bin/timeout --kill-after=30s 45m python3 "$task_root/control/download-molmobot.py" --execute
