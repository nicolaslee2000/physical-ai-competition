#!/usr/bin/env bash
# Run only after the active placement comparison has released the task job slot.
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
[[ "$task_root" == /opt/hderc-internal/nick/physical-ai-competition && "$(id -u)" == 1006 ]] || exit 2
[[ -n "${INVOCATION_ID:-}" ]] || { echo 'Launch through control/start-job.sh.' >&2; exit 2; }
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
[[ "$(systemctl --user show nick-physical-ai-eval.service --property=InvocationID --value)" == "$INVOCATION_ID" ]] || exit 2
python3 "$task_root/control/guard.py" check
plan="$task_root/experiments/plan-groot-smoke.json"
recordings="$task_root/experiments/results/20261102T223003Z-e2ae990e/baseline/episodes"
python="$task_root/positronic/.venv/bin/python"
# Existing runners each hold eval.lock and clean up their own policy/network.
# Session qualification is separate evidence; task success comes only from the development run.
"$python" "$task_root/experiments/qualify_images.py" --plan "$plan" --recordings "$recordings" --execute
python3 "$task_root/control/guard.py" check
"$python" "$task_root/experiments/local_eval.py" --config "$plan" --execute
python3 "$task_root/control/guard.py" check
