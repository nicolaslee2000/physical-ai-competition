#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
[[ "$task_root" == /opt/hderc-internal/nick/physical-ai-competition && "$(id -u)" == 1006 ]] || exit 2
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
[[ -n "${INVOCATION_ID:-}" && "$(systemctl --user show nick-physical-ai-eval.service --property=InvocationID --value)" == "$INVOCATION_ID" ]] || exit 2
python3 "$task_root/control/guard.py" check
python3 - "$task_root" <<'PY'
from pathlib import Path
import json,re,sys
r=Path(sys.argv[1]);image=json.loads((r/'state/molmobot-image.json').read_text())['image']
assert re.fullmatch(r'sha256:[a-f0-9]{64}',image)
plan={'repo':str(r/'positronic'),'python':str(r/'positronic/.venv/bin/python'),
      'ready_timeout_s':600,'policies':[
        {'name':'baseline','image':'positro/molmoact2-droid@sha256:53be1ce8e9c6456626987720b08d713fa6d2c62eb4b4b9338393d5e4e35802b6'},
        {'name':'molmobot-droid','image':image}],
      'comparison_note':'Stock MolmoAct2 versus MolmoBot native session qualification; no task score'}
(r/'experiments/plan-molmobot-native.json').write_text(json.dumps(plan,indent=2)+'\n')
PY
exec "$task_root/positronic/.venv/bin/python" "$task_root/experiments/qualify_molmobot.py" \
  --plan "$task_root/experiments/plan-molmobot-native.json" \
  --recordings "$task_root/experiments/results/20261102T223003Z-e2ae990e/baseline/episodes" --execute
