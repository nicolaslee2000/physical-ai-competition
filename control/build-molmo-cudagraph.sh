#!/usr/bin/env bash
# Preparation only until coordinator launches this through start-job.sh.
set -euo pipefail
umask 077
task_root=$(cd "$(dirname "$0")/.." && pwd)
[[ "$task_root" == /opt/hderc-internal/nick/physical-ai-competition && "$(id -u)" == 1006 ]] || exit 2
[[ -n "${INVOCATION_ID:-}" ]] || { echo 'Launch only through control/start-job.sh.' >&2; exit 2; }
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
unit_invocation=$(systemctl --user show nick-physical-ai-eval.service --property=InvocationID --value)
[[ "$unit_invocation" == "$INVOCATION_ID" ]] || { echo 'This is not the task job service.' >&2; exit 2; }
python3 "$task_root/control/guard.py" check
# The start-job service excludes other task jobs; the shared lock also excludes direct eval/qualification runners.
exec 9>"$task_root/experiments/eval.lock"
flock -n 9 || { echo 'An evaluation or qualification owns the task lock.' >&2; exit 2; }
python3 - "$task_root" <<'VALIDATE'
import hashlib
from pathlib import Path
import sys

SOURCE_SHA = '17701668590b19179ba5cf62ea3359271f3a8a88775aad4e30b034dc8d9fe212'
BASE = 'positro/molmoact2-droid@sha256:53be1ce8e9c6456626987720b08d713fa6d2c62eb4b4b9338393d5e4e35802b6'


def validate(root, source_sha=SOURCE_SHA):
    source = root / 'experiments/candidates/Dockerfile.molmoact2-cudagraphs'
    for path in (root / 'tmp', root / 'state', source):
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Build path escapes task root')
        for ancestor in (path, *path.parents):
            if ancestor.is_symlink():
                raise ValueError('Symlink in build path')
            if ancestor == root:
                break
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != source_sha:
        raise ValueError('Reviewed Dockerfile changed; review and repin it first')
    instructions = [line.strip() for line in raw.decode().splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if len(instructions) != 2 or instructions[0] != 'FROM ' + BASE or not instructions[1].startswith('RUN '):
        raise ValueError('Only the pinned base and reviewed source-toggle RUN are authorized')
    return source


if __name__ == '__main__':
    validate(Path(sys.argv[1]))
VALIDATE
engine=(bash "$task_root/docker/engine.sh")
security=$("${engine[@]}" info --format '{{json .SecurityOptions}}')
[[ "$security" == *rootless* ]] || { echo 'Dedicated engine must be rootless.' >&2; exit 2; }
base='positro/molmoact2-droid@sha256:53be1ce8e9c6456626987720b08d713fa6d2c62eb4b4b9338393d5e4e35802b6'
# Fail before build if this exact digest is not already cached. No pull is authorized.
base_id=$("${engine[@]}" image inspect "$base" --format '{{.Id}}')
context=$(mktemp -d "$task_root/tmp/molmo-cudagraph-context.XXXXXXXX")
cleanup() {
  python3 - "$task_root" "$context" <<'CLEANUP'
from pathlib import Path
import sys
root, context = map(Path, sys.argv[1:])
if context.is_symlink() or not context.resolve().is_relative_to((root / 'tmp').resolve()):
    raise ValueError('Refuse unsafe context cleanup')
for path in context.iterdir():
    if path.name not in ('Dockerfile', '.dockerignore') or path.is_symlink() or not path.is_file():
        raise ValueError('Unexpected context entry; preserve for review')
for path in context.iterdir():
    path.unlink()
context.rmdir()
CLEANUP
}
trap cleanup EXIT
cp -- "$task_root/experiments/candidates/Dockerfile.molmoact2-cudagraphs" "$context/Dockerfile"
printf '*\n!Dockerfile\n' > "$context/.dockerignore"
python3 - "$context" <<'CONTEXT'
import hashlib
from pathlib import Path
import sys
context=Path(sys.argv[1])
if {path.name for path in context.iterdir()} != {'Dockerfile','.dockerignore'} or any(path.is_symlink() for path in context.iterdir()):
    raise ValueError('Context must contain exactly two regular build files')
if hashlib.sha256((context/'Dockerfile').read_bytes()).hexdigest() != '17701668590b19179ba5cf62ea3359271f3a8a88775aad4e30b034dc8d9fe212':
    raise ValueError('Context Dockerfile differs from reviewed source')
CONTEXT
# Explicit context contains no repository, data, weights, credentials or external build inputs.
run_id=$(python3 -c 'import datetime,uuid;print(datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:8])')
tag="nick/physical-ai:molmo-cudagraph-$run_id"
python3 "$task_root/control/guard.py" check
/usr/bin/timeout --kill-after=30s 15m "${engine[@]}" buildx build --builder default --platform linux/amd64 \
  --pull=false --network=none --provenance=false --sbom=false --load \
  -f "$context/Dockerfile" -t "$tag" "$context"
image_id=$("${engine[@]}" image inspect "$tag" --format '{{.Id}}')
python3 "$task_root/control/guard.py" check
python3 - "$task_root" "$run_id" "$tag" "$image_id" "$base" "$base_id" <<'RECORD'
import datetime
import json
from pathlib import Path
import re
import sys
root=Path(sys.argv[1]);run_id,tag,image_id,base,base_id=sys.argv[2:]
if not all(re.fullmatch(r'sha256:[0-9a-f]{64}', value) for value in (image_id,base_id)):
    raise ValueError('Engine did not return exact immutable local config IDs')
record={'name':'molmoact2-cudagraphs','local_tag':tag,'image':image_id,'identity_kind':'local_docker_config_sha256',
        'base_manifest_digest':base,'base_local_config_id':base_id,
        'built_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status':'built_unmeasured','no_official_submission':True,
        'scope':'CUDA graph source toggle only; no model inference or measured improvement'}
path=root/'state'/('molmo-cudagraph-image-'+run_id+'.json')
with path.open('x') as stream:
    json.dump(record,stream,indent=2);stream.write('\n')
print(json.dumps({'record':str(path),'image':image_id}))
RECORD
