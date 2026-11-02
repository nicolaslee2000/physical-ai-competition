#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
export DOCKER_HOST="unix://$task_root/runtime/docker.sock"
export DOCKER_CONFIG="$task_root/config/docker"
export TMPDIR="$task_root/tmp"
export XDG_CACHE_HOME="$task_root/cache"
exec docker "$@"
