#!/usr/bin/env bash
# Bounded source acquisition only. No GPU, model load or evaluator installation.
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
[[ "$task_root" == /opt/hderc-internal/nick/physical-ai-competition && "$(id -u)" == 1006 ]] || exit 2
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
[[ -n "${INVOCATION_ID:-}" && "$(systemctl --user show nick-physical-ai-eval.service --property=InvocationID --value)" == "$INVOCATION_ID" ]] || exit 2
exec 9>"$task_root/experiments/eval.lock"
flock -n 9 || exit 2
python3 "$task_root/control/guard.py" check
stage="$task_root/packaging/molmobot"
mkdir -p "$stage/src" "$stage/notices" "$stage/logs" "$stage/wheelhouse" "$stage/tmp" "$stage/cache"
export TMPDIR="$stage/tmp" XDG_CACHE_HOME="$stage/cache"
source_dir="$stage/src/MolmoBot"
revision=33c0ca77bf6062a23d60ffd4a6859334c4a46d30
if [[ ! -d "$source_dir/.git" ]]; then
  git init -q "$source_dir"
  git -C "$source_dir" remote add origin https://github.com/allenai/MolmoBot.git
fi
if ! git -C "$source_dir" cat-file -e "$revision^{commit}" 2>/dev/null; then
  /usr/bin/timeout --kill-after=10s 180s git -c credential.helper= -C "$source_dir" fetch --depth=1 origin "$revision"
fi
[[ -z "$(git -C "$source_dir" status --porcelain)" ]] || exit 2
git -C "$source_dir" checkout --detach "$revision"
[[ "$(git -C "$source_dir" rev-parse HEAD)" == "$revision" ]] || exit 2
positronic_rev=00fdd933f22158a9cbe6d97c5b19c2935df35c1b
if [[ ! -d "$stage/src/positronic" ]]; then
  mkdir "$stage/src/positronic"
  git -C "$task_root/positronic" archive "$positronic_rev" | tar -x -C "$stage/src/positronic"
fi
python3 "$task_root/control/guard.py" check
python3 - "$stage" "$revision" "$positronic_rev" <<'PY'
from pathlib import Path
import sys,json,hashlib,datetime,shutil
p=Path(sys.argv[1]);rows=[]
for repo in ['MolmoBot','positronic']:
 for f in (p/'src'/repo).rglob('*'):
  if '.git' in f.parts or not f.is_file():continue
  if f.name.upper().startswith(('LICENSE','NOTICE','COPYING')):
   dest=p/'notices'/repo/f.relative_to(p/'src'/repo)
   dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dest)
  if f.name in ('pyproject.toml','uv.lock','LICENSE','README.md'):
   rows.append({'path':str(f.relative_to(p)),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
out={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'molmobot_revision':sys.argv[2],'positronic_revision':sys.argv[3],'files':rows,'stage':'source_acquired_only','model_loaded':False}
(p/'source-manifest.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'stage':out['stage'],'manifest_files':len(rows)}))
PY
