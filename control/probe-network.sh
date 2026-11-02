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
  -p 127.0.0.1:18080:8000 --entrypoint /positronic/.venv/bin/python \
  positro/pi05-droid@sha256:94ef6b483f460b2453cc0e555668e84af0eb790b9598aabbadc406382ef6ca2f \
  -m http.server 8000 >/dev/null
for attempt in $(seq 1 30); do
  if curl --noproxy '*' -fsS -m 1 http://127.0.0.1:18080/ >/dev/null; then
    echo 'Rootless internal-network loopback forwarding verified.'
    "${d[@]}" exec "$name" /positronic/.venv/bin/python -c 'import socket; s=socket.socket(); s.settimeout(2); r=s.connect_ex(("1.1.1.1",443)); assert r != 0; print("Policy network egress is blocked.")'
    exit 0
  fi
  sleep 0.5
done
echo 'Rootless loopback forwarding failed; do not launch the evaluator.' >&2
exit 1
