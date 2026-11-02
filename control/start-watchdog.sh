#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$task_root/state" "$task_root/logs"
user_runtime="/run/user/$(id -u)"
XDG_RUNTIME_DIR="$user_runtime" systemd-run --user --unit=nick-physical-ai-watchdog --collect \
  --property=MemoryMax=64M --property=TimeoutStopSec=15s \
  --property="StandardOutput=append:$task_root/logs/watchdog.log" \
  --property="StandardError=append:$task_root/logs/watchdog.log" \
  /usr/bin/python3 "$task_root/control/guard.py" watch
# Trigger slightly early so graceful shutdown finishes before 08:30 Berlin.
XDG_RUNTIME_DIR="$user_runtime" systemd-run --user --unit=nick-physical-ai-deadline --collect \
  --on-calendar='2026-11-03 07:29:30 UTC' --timer-property=AccuracySec=1s \
  --property="StandardOutput=append:$task_root/logs/deadline.log" \
  --property="StandardError=append:$task_root/logs/deadline.log" \
  /usr/bin/python3 "$task_root/control/guard.py" stop
