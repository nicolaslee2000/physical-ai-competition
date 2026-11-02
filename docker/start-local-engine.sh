#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$task_root"/{runtime,tmp,config,cache,storage,logs}
chmod 700 "$task_root"/{runtime,tmp,config,cache,storage,logs}
cat > "$task_root/config/daemon.json" <<'JSON'
{
  "features": {"containerd-snapshotter": false, "cdi": true},
  "storage-driver": "overlay2",
  "exec-opts": ["native.cgroupdriver=systemd"],
  "max-concurrent-downloads": 2,
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "1"}
}
JSON
user_runtime="/run/user/$(id -u)"
cpu_list=$(python3 -c 'import os; print(",".join(map(str, sorted(os.sched_getaffinity(0))[:4])))')
XDG_RUNTIME_DIR="$user_runtime" systemd-run --user --unit=nick-physical-ai-docker --collect \
  --property=Delegate=yes --property=MemoryMax=28G --property=MemorySwapMax=0 \
  --property=TimeoutStopSec=15s --property=KillMode=control-group \
  --property=CPUQuota=400% \
  --property="StandardOutput=append:$task_root/logs/engine.log" \
  --property="StandardError=append:$task_root/logs/engine.log" \
  /usr/bin/taskset --cpu-list "$cpu_list" /usr/bin/env \
  "XDG_RUNTIME_DIR=$task_root/runtime" "XDG_CONFIG_HOME=$task_root/config" \
  "XDG_DATA_HOME=$task_root/storage" "XDG_CACHE_HOME=$task_root/cache" \
  "DOCKER_CONFIG=$task_root/config/docker" "TMPDIR=$task_root/tmp" \
  "DBUS_SESSION_BUS_ADDRESS=unix:path=$user_runtime/bus" \
  /usr/bin/dockerd-rootless.sh \
  --config-file "$task_root/config/daemon.json" \
  --data-root "$task_root/storage/docker" --exec-root "$task_root/runtime/exec" \
  --pidfile "$task_root/runtime/docker.pid" \
  --host "unix://$task_root/runtime/docker.sock"
