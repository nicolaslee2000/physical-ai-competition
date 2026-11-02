#!/usr/bin/env python3
"""Fail-closed gates for one explicitly authorized overnight run. No credentials."""
import argparse
import datetime as dt
import json
import pathlib
import subprocess
import shutil
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]


def decision(policy, snapshot, now, gpu=False, stopped=False):
    if stopped:
        return False, "manual stop requested"
    deadline = dt.datetime.fromisoformat(policy["deadline"]).timestamp()
    margin = policy["stop_gpu_seconds_before_deadline"] if gpu else policy["stop_new_work_seconds_before_deadline"]
    if now >= deadline - margin:
        return False, "deadline reached"
    try:
        age = now - float(snapshot["collected_at"])
        windows = snapshot["remaining_percent"]
        if not isinstance(windows, list) or not windows:
            raise ValueError("missing usage windows")
        remaining = min(float(x) for x in windows)
        if not 0 <= remaining <= 100 or age < -30:
            raise ValueError("invalid usage")
    except (KeyError, TypeError, ValueError):
        return False, "usage unavailable"
    if age > policy["usage_snapshot_max_age_seconds"]:
        return False, "usage snapshot expired"
    if remaining <= policy["usage_stop_remaining_percent"]:
        return False, "usage reserve reached"
    return True, "within deadline and usage reserve"


def read_state():
    policy = json.loads((ROOT / "control/policy.json").read_text())
    try:
        snapshot = json.loads((ROOT / "state/usage.json").read_text())
    except (OSError, ValueError):
        snapshot = {}
    return policy, snapshot


def stop(reason):
    state = ROOT / "state"
    state.mkdir(exist_ok=True)
    (state / "stopped.json").write_text(json.dumps({"reason": reason, "at": dt.datetime.now(dt.timezone.utc).isoformat()}, indent=2) + "\n")
    # Only task-owned transient units. Never address the shared Docker engine.
    import os
    env = dict(os.environ, XDG_RUNTIME_DIR=f"/run/user/{os.getuid()}")
    for unit in ("nick-physical-ai-eval", "nick-physical-ai-docker"):
        subprocess.run(["systemctl", "--user", "stop", unit], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25, check=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["check", "watch", "stop"])
    args = parser.parse_args()
    if args.mode == "stop":
        stop("scheduled or explicit stop")
        return
    while True:
        try:
            policy, snapshot = read_state()
            allowed, reason = decision(policy, snapshot, time.time(), gpu=args.mode == "watch", stopped=(ROOT / "state/STOP").exists() or (ROOT / "state/stopped.json").exists())
            if allowed and shutil.disk_usage(ROOT).free < policy["min_disk_free_bytes"]:
                allowed, reason = False, "disk reserve reached"
        except (OSError, ValueError, KeyError) as exc:
            allowed, reason = False, "invalid control configuration: " + type(exc).__name__
        if args.mode == "check":
            print(json.dumps({"allowed": allowed, "reason": reason}))
            raise SystemExit(0 if allowed else 2)
        if not allowed:
            stop(reason)
            return
        time.sleep(15)


if __name__ == "__main__":
    main()
