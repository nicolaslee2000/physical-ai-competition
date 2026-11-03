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
PYTHONPATH="$task_root/experiments" /usr/bin/timeout --kill-after=15s 10m python3 -m molmobot_candidate.stage_image
python3 "$task_root/control/guard.py" check
context=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["context"])' "$stage/image-build-plan.json")
run_id=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["run_id"])' "$stage/image-build-plan.json")
tag="nick/physical-ai:molmobot-$run_id"
engine=(bash "$task_root/docker/engine.sh")
[[ "$("${engine[@]}" info --format '{{json .SecurityOptions}}')" == *rootless* ]] || exit 2
base='pytorch/pytorch@sha256:417bd75df6365104c283ea4c1651fb3530d9eb5a4c2fafa51943cff2a94e6385'
"${engine[@]}" image inspect "$base" --format '{{.Id}}' > "$stage/build-base-id.txt"
/usr/bin/timeout --kill-after=30s 20m "${engine[@]}" buildx build --builder default --platform linux/amd64 \
  --pull=false --network=none --provenance=false --sbom=false --load \
  -f "$context/Dockerfile" -t "$tag" "$context" > "$stage/logs/image-build.log" 2>&1
image_id=$("${engine[@]}" image inspect "$tag" --format '{{.Id}}')
python3 "$task_root/control/guard.py" check
python3 - "$task_root" "$tag" "$image_id" <<'PY'
from pathlib import Path
import datetime,json,re,sys
root=Path(sys.argv[1]);tag,image=sys.argv[2:]
assert re.fullmatch(r'sha256:[a-f0-9]{64}',image)
stage=root/'packaging/molmobot'
plan=json.loads((stage/'image-build-plan.json').read_text())
out={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'image':image,'local_tag':tag,
     'identity_kind':'local_config_id_not_registry_digest','status':'built_unqualified_native_server',
     'lock_sha256':plan['requirements_sha256'],'dockerfile_sha256':plan['dockerfile_sha256'],
     'context':plan['context'],'scope':'Offline package built; single-process probe passed separately; native sessions and task scores pending',
     'official_submission':False}
(root/'state/molmobot-image.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out))
PY
