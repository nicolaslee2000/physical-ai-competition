#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
[[ "$task_root" == /opt/hderc-internal/nick/physical-ai-competition && "$(id -u)" == 1006 ]] || exit 2
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
[[ -n "${INVOCATION_ID:-}" && "$(systemctl --user show nick-physical-ai-eval.service --property=InvocationID --value)" == "$INVOCATION_ID" ]] || exit 2
exec 9>"$task_root/experiments/eval.lock"
flock -n 9 || exit 2
python3 "$task_root/control/guard.py" check
stage="$task_root/packaging/molmobot"
[[ -f "$stage/runtime-manifest.json" ]] || exit 2
mkdir -p "$stage/probe"
# Read one already-consumed public development recording. No simulator is started.
PYTHONPATH="$task_root/experiments" "$task_root/positronic/.venv/bin/python" - "$stage" <<'PY'
from pathlib import Path
import hashlib,json,sys,numpy as np
from qualify_sessions import load_development
p=Path(sys.argv[1]);manifest=json.loads((p/'runtime-manifest.json').read_text())
assert manifest['stage']=='resolved_and_imported'
assert hashlib.sha256((p/'requirements.lock').read_bytes()).hexdigest()==manifest['lock_sha256']
for row in manifest['wheels']:
 f=p/'wheelhouse'/row['file']
 assert f.stat().st_size==row['bytes'] and hashlib.sha256(f.read_bytes()).hexdigest()==row['sha256']
recordings=Path('/opt/hderc-internal/nick/physical-ai-competition/experiments/results/20261102T223003Z-e2ae990e/baseline/episodes')
obs,index=load_development(recordings)
np.savez(p/'probe/observation.npz',joints=obs['robot_state.q'],grip=obs['grip'],
         exterior=obs['image.exterior'],wrist=obs['image.wrist'],task=np.asarray(obs['task']))
(p/'probe/observation-provenance.json').write_text(json.dumps({'recordings':str(recordings),'development_index':index,'purpose':'runtime shapes only'})+'\n')
PY
python3 "$task_root/control/guard.py" check
engine=(bash "$task_root/docker/engine.sh")
[[ "$("${engine[@]}" info --format '{{json .SecurityOptions}}')" == *rootless* ]] || exit 2
name=physical-ai-molmobot-probe
cleanup() {
  "${engine[@]}" inspect --format '{"status":"{{.State.Status}}","exit_code":{{.State.ExitCode}},"oom_killed":{{.State.OOMKilled}}}' "$name" > "$stage/probe/container-state.json" 2>/dev/null || true
  "${engine[@]}" rm -f "$name" >/dev/null 2>&1 || true
}
trap cleanup EXIT
base='pytorch/pytorch@sha256:417bd75df6365104c283ea4c1651fb3530d9eb5a4c2fafa51943cff2a94e6385'
/usr/bin/timeout --kill-after=30s 15m "${engine[@]}" run --pull=never --name "$name" --network=none \
  --device nvidia.com/gpu=GPU-7c4310dd-d211-6c65-506c-2a74f693fe8b \
  --memory=28g --memory-swap=28g \
  --mount "type=bind,src=$stage,dst=$stage" \
  --mount "type=bind,src=$task_root/artifacts/molmobot,dst=$task_root/artifacts/molmobot,readonly" \
  --mount "type=bind,src=$task_root/experiments/molmobot_candidate,dst=$task_root/experiments/molmobot_candidate,readonly" \
  -e "PYTHONPATH=$task_root/experiments" -e "TMPDIR=$stage/tmp" \
  -e "XDG_CACHE_HOME=$stage/cache" -e "PIP_CACHE_DIR=$stage/cache/pip" \
  -e PIP_NO_INDEX=1 -e PIP_NO_INPUT=1 -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 -e HF_HUB_DISABLE_TELEMETRY=1 \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 \
  "$base" bash -euc '
    stage=/opt/hderc-internal/nick/physical-ai-competition/packaging/molmobot
    python -m venv --system-site-packages "$stage/probe/runtime-venv"
    "$stage/probe/runtime-venv/bin/python" -m pip install --no-index --no-deps --require-hashes --find-links="$stage/wheelhouse" -r "$stage/requirements.lock"
    "$stage/probe/runtime-venv/bin/python" -m pip check
    exec "$stage/probe/runtime-venv/bin/python" -m molmobot_candidate.probe_runtime
  ' > "$stage/probe/runtime.log" 2>&1
python3 "$task_root/control/guard.py" check
