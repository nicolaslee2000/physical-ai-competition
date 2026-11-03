#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
# Validate the optional policy date before changing any service state.
deadline_calendar=$(python3 - "$task_root" <<'PY'
import datetime as dt
import json
import math
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(sys.argv[1]) / 'control'))
from guard import optional_deadline
policy = json.loads((pathlib.Path(sys.argv[1]) / 'control/policy.json').read_text())
deadline = optional_deadline(policy.get('deadline'))
if deadline is not None:
    margin = policy['stop_gpu_seconds_before_deadline']
    if type(margin) not in (int, float) or not math.isfinite(margin) or margin < 0:
        raise ValueError('Invalid shutdown margin')
    print(dt.datetime.fromtimestamp(deadline - margin, dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))
PY
)
mkdir -p "$task_root/state" "$task_root/logs"
exec 9>"$task_root/state/watchdog-start.lock"
flock -n 9
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
# Stop only our own prior deadline units. Missing units are safe; other errors fail closed.
for unit in nick-physical-ai-deadline.timer nick-physical-ai-deadline.service; do
  if state=$(systemctl --user show --property=LoadState --value "$unit"); then
    if [[ "$state" != "not-found" ]]; then
      systemctl --user stop "$unit"
    fi
  elif [[ "$state" != "not-found" ]]; then
    exit 1
  fi
done
if ! systemctl --user is-active --quiet nick-physical-ai-watchdog; then
  systemd-run --user --unit=nick-physical-ai-watchdog --collect \
    --property=MemoryMax=64M --property=TimeoutStopSec=15s \
    --property="StandardOutput=append:$task_root/logs/watchdog.log" \
    --property="StandardError=append:$task_root/logs/watchdog.log" \
    /usr/bin/python3 "$task_root/control/guard.py" watch
fi
# Null policy deadline leaves the quota/freshness/manual-stop/disk watcher running.
if [[ -n "$deadline_calendar" ]]; then
  systemd-run --user --unit=nick-physical-ai-deadline --collect \
    --on-calendar="$deadline_calendar" --timer-property=AccuracySec=1s \
    --property="StandardOutput=append:$task_root/logs/deadline.log" \
    --property="StandardError=append:$task_root/logs/deadline.log" \
    /usr/bin/python3 "$task_root/control/guard.py" stop
fi
