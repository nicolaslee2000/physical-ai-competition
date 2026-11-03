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
stage="$task_root/packaging/molmobot"
cp "$task_root/artifacts/molmobot/checkpoint/config.yaml" "$stage/checkpoint-config.yaml"
if [[ -f "$stage/logs/resolve-runtime.log" ]]; then
  cp "$stage/logs/resolve-runtime.log" "$stage/logs/resolve-runtime-previous-$(date -u +%Y%m%dT%H%M%SZ).log"
fi
name=physical-ai-molmobot-resolver
cleanup() { "${engine[@]}" rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT
base='pytorch/pytorch@sha256:417bd75df6365104c283ea4c1651fb3530d9eb5a4c2fafa51943cff2a94e6385'
# No GPU devices, secrets, evaluator mounts or model weights enter this container.
/usr/bin/timeout --kill-after=30s 45m "${engine[@]}" run --rm --pull=never --name "$name" \
  --memory=8g --memory-swap=8g \
  --mount "type=bind,src=$stage,dst=$stage" \
  --mount "type=bind,src=$task_root/artifacts/molmobot/tokenizer,dst=$task_root/artifacts/molmobot/tokenizer,readonly" \
  --mount "type=bind,src=$task_root/experiments/molmobot_candidate,dst=$task_root/experiments/molmobot_candidate,readonly" \
  -e "PYTHONPATH=$task_root/experiments" -e "TMPDIR=$stage/tmp" \
  -e "XDG_CACHE_HOME=$stage/cache" -e "PIP_CACHE_DIR=$stage/cache/pip" \
  -e PIP_NO_INPUT=1 -e PIP_DISABLE_PIP_VERSION_CHECK=1 -e PIP_DEFAULT_TIMEOUT=30 \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 -e HF_HUB_DISABLE_TELEMETRY=1 \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 \
  "$base" python "$task_root/experiments/molmobot_candidate/resolve_runtime.py" "$@" \
  > "$stage/logs/resolve-runtime.log" 2>&1
python3 "$task_root/control/guard.py" check
