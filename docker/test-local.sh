#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
export DOCKER_HOST="unix://$task_root/runtime/docker.sock"
export DOCKER_CONFIG="$task_root/config/docker"
export TMPDIR="$task_root/tmp"
export POLICY_TEST_ROOTLESS_STATE="$task_root/runtime/dockerd-rootless"
export POLICY_TEST_GPU=GPU-7c4310dd-d211-6c65-506c-2a74f693fe8b
exec bash "$task_root/docker/test_policy_image.sh" --gpu "$@"
