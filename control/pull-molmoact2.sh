#!/usr/bin/env bash
# Run only through start-job.sh; the dedicated engine keeps every layer in nick/.
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
python3 "$task_root/control/guard.py" check
free_bytes=$(python3 -c 'import shutil,sys;print(shutil.disk_usage(sys.argv[1]).free)' "$task_root")
# Keep the 60 GiB reserve plus 80 GiB temporary pull/unpack headroom.
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
image='positro/molmoact2-droid@sha256:53be1ce8e9c6456626987720b08d713fa6d2c62eb4b4b9338393d5e4e35802b6'
/usr/bin/timeout --signal=TERM --kill-after=15s 1800 "${engine[@]}" pull "$image"
python3 "$task_root/control/guard.py" check
"${engine[@]}" image inspect --format '{{.Id}} {{.Architecture}} {{.Size}}' "$image"
