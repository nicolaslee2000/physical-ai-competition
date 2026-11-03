#!/usr/bin/env bash
# Launch via start-job.sh only after active GPU comparisons end.
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
python3 "$task_root/control/guard.py" check
free_bytes=$(python3 -c 'import shutil,sys;print(shutil.disk_usage(sys.argv[1]).free)' "$task_root")
# 60 GiB reserve plus 80 GiB pull/unpack headroom.
if (( free_bytes < 150323855360 )); then
  echo 'Insufficient reserved pull/unpack disk space.' >&2
  exit 2
fi
engine=(bash "$task_root/docker/engine.sh")
storage=$("${engine[@]}" info --format '{{.DockerRootDir}}')
if [[ "$storage" != "$task_root/storage/docker" ]]; then
  echo 'Unexpected Docker storage directory.' >&2
  exit 2
fi
image='docker.io/positro/gr00t-n17-droid@sha256:cf3a4f0ab524bc776f3ae9ee5cc972d0b3cfb0caa0c42d2cb73d2805b4281f39'
/usr/bin/timeout --signal=TERM --kill-after=15s 1800 "${engine[@]}" pull "$image"
python3 "$task_root/control/guard.py" check
"${engine[@]}" image inspect --format '{{.Id}} {{.Architecture}} {{.Size}}' "$image"
