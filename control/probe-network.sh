#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
python3 "$task_root/control/guard.py" check
d=(bash "$task_root/docker/engine.sh")
name=nick-physical-ai-network-probe
net=nick-physical-ai-network-probe
cleanup() { "${d[@]}" rm -f "$name" >/dev/null 2>&1 || true; "${d[@]}" network rm "$net" >/dev/null 2>&1 || true; }
trap cleanup EXIT
"${d[@]}" network create --internal "$net" >/dev/null
"${d[@]}" run --rm -d --name "$name" --network "$net" --memory=256m --memory-swap=256m \
  --entrypoint /bin/sh \
  positro/pi05-droid@sha256:94ef6b483f460b2453cc0e555668e84af0eb790b9598aabbadc406382ef6ca2f \
  -c 'printf nick-physical-ai-netprobe-v1 > /tmp/probe.txt; exec /positronic/.venv/bin/python -m http.server 8000 --directory /tmp' >/dev/null
ip=$("${d[@]}" inspect --format "{{(index .NetworkSettings.Networks \"$net\").IPAddress}}" "$name")
child_pid=$(cat "$task_root/runtime/dockerd-rootless/child_pid")
probe=(nsenter --user="/proc/$child_pid/ns/user" --mount="/proc/$child_pid/ns/mnt" --preserve-credentials nsenter --net="$task_root/runtime/dockerd-rootless/netns")
for attempt in $(seq 1 30); do
  if [ "$("${probe[@]}" /usr/bin/curl --noproxy '*' -fsS -m 1 "http://$ip:8000/probe.txt" 2>/dev/null || true)" = nick-physical-ai-netprobe-v1 ]; then
    echo 'Rootless engine namespace reaches the isolated policy container.'
    "${d[@]}" exec "$name" /positronic/.venv/bin/python -c 'import socket; s=socket.socket(); s.settimeout(2); r=s.connect_ex(("1.1.1.1",443)); assert r != 0; print("Policy network egress is blocked.")'
    exit 0
  fi
  sleep 0.5
done
echo 'Rootless namespace probe failed; do not launch the evaluator.' >&2
exit 1
