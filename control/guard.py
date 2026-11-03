#!/usr/bin/env python3
"""Fail-closed gates for one explicitly authorized overnight run. No credentials."""
import argparse
import datetime as dt
import json
import math
import pathlib
import subprocess
import shutil
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]


def optional_deadline(value):
    """Null/missing is explicitly unbounded; dated policies require an aware ISO timestamp."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('deadline must be null or an ISO timestamp')
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('deadline must include a timezone')
    result = parsed.timestamp()
    if not math.isfinite(result):
        raise ValueError('invalid deadline')
    return result


def decision(policy, snapshot, now, gpu=False, stopped=False):
    if stopped:
        return False, "manual stop requested"
    try:
        deadline = optional_deadline(policy.get('deadline'))
        margin = policy["stop_gpu_seconds_before_deadline"] if gpu else policy["stop_new_work_seconds_before_deadline"]
        max_age, reserve = policy['usage_snapshot_max_age_seconds'], policy['usage_stop_remaining_percent']
        for value in (margin, max_age, reserve):
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError('invalid control limit')
        if max_age <= 0 or reserve > 100:
            raise ValueError('invalid usage limits')
    except (KeyError, TypeError, ValueError, OverflowError):
        return False, 'invalid control configuration'
    if deadline is not None and now >= deadline - margin:
        return False, "deadline reached"
    try:
        collected = snapshot['collected_at']
        windows = snapshot['remaining_percent']
        if type(collected) not in (int, float) or not math.isfinite(collected):
            raise ValueError('invalid snapshot timestamp')
        if not isinstance(windows, list) or not windows or any(type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100 for value in windows):
            raise ValueError('missing/invalid usage windows')
        age = now - collected
        remaining = min(windows)
        if age < -30:
            raise ValueError('future usage timestamp')
    except (KeyError, TypeError, ValueError):
        return False, "usage unavailable"
    if age > max_age:
        return False, "usage snapshot expired"
    if remaining <= reserve:
        return False, "usage reserve reached"
    return True, "within usage reserve and optional deadline"


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
        except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
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
