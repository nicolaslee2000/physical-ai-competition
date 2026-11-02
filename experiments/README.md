# Bounded public-practice comparison

This checkout provides the harness; measured results must come from its verified run artifacts. `plan.json` contains the pinned official baseline twice as a reproducibility control. Replace the second image with a locally available, digest-pinned candidate before comparing a change. No candidate improvements are claimed.

All host files, model downloads, Docker engine state, assets, temporary files and Python environments must live below `/opt/hderc-internal/nick/physical-ai-competition/`. Deploy this directory as that root's `experiments/`; the existing dedicated wrapper must be at `docker/engine.sh`. The wrapper must target its dedicated rootless socket and store its engine state inside this task root. The runner additionally checks Docker reports rootless and never uses another Docker entry point. It never pulls or builds an image, contacts the official evaluation platform, reads API credentials, or invokes SSH.

## Prerequisites before executing on the isolated Linux host

- Linux amd64, sufficient disk (upstream estimates about 80 GB), rootless NVIDIA Container Toolkit integration tested for the dedicated engine, and the UUID `GPU-7c4310dd-d211-6c65-506c-2a74f693fe8b` available for authorized experimentation.
- Upstream Positronic checkout at the `repo` path in `plan.json`, with its dependencies and CLI installed in its `.venv`. Its Python interpreter must resolve inside the task root (use uv-managed Python installed under the task root). The checked-out source and installed package must match; record the git revision with results. The checker imports the checkout's actual `integration_tests/molmo_local_eval.py` and installed `positronic_evals`.
- `uv` 0.8.5 or newer available at `bin/uv`, with managed Python/environment/cache/downloads all in the task root. Upstream hardcodes both MolmoSpaces source/environment cache and env-server port locks under `Path.home()`. Before evaluation apply the supplied exact-source patch using `prepare_cache_patch.py`; it redirects only those two paths through `PHYSICAL_AI_CACHE_DIR` into the task cache, without changing `HOME` or `CODEX_HOME`. A source checkout installed editable is required. The runner checks both patch text and installed runtime paths before accessing Docker.
- Digest-pinned policy images or immutable local config IDs already present in the dedicated engine; image entrypoints must serve port 8000 and support `POST /api/v1/keepalive`. Model weights must be baked into the image or otherwise accessible within the dedicated engine state, without external credentials. The baseline uses baked-in `/opt/positronic/...` paths *inside its image*; host model/cache paths remain in the isolated task root. This harness does not rewrite arbitrary image entrypoints or runtime model lookup paths.
- `/usr/bin/nsenter` and `/usr/bin/curl` installed on the host; the dedicated rootless daemon writes `runtime/dockerd-rootless/child_pid` and `netns` below the task root. No host port is published. Use only the available GPU headroom; preserve production workloads. CDI exposes the UUID and JAX allocation is limited to a 0.16 fraction with preallocation disabled. This is not a hard GPU-memory partition. The simulator uses upstream's supported software EGL setting, so policy inference alone uses the GPU. This is slower; initial asset/environment installation is included in the timeout and may require preparation before comparison.

## Plan and run

A plan is safe to inspect on the laptop:

```sh
python3 competition/experiments/local_eval.py
```

The previous published-port approach does not work for this rootless internal network and has been removed. The runner now inspects the actual policy container IP and enters the dedicated daemon network namespace for readiness, evaluation and timing reduction. This updated full path still needs live verification. After preparing the isolated checkout and uv-managed environment, apply the cache patch (does not launch a GPU job):

```sh
/usr/bin/python3 /opt/hderc-internal/nick/physical-ai-competition/experiments/prepare_cache_patch.py
```

Install the patched checkout editable in its task-local `.venv`, using task-local `UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR`, `XDG_CACHE_HOME`, and `TMPDIR`; leave `HOME` and `CODEX_HOME` untouched. The project uses `uv sync --locked` for its environment. Do not use a globally installed Positronic CLI. Once prerequisites are checked, launch only through the watchdog wrapper:

```sh
bash /opt/hderc-internal/nick/physical-ai-competition/control/start-job.sh \
  /opt/hderc-internal/nick/physical-ai-competition/positronic/.venv/bin/python \
  /opt/hderc-internal/nick/physical-ai-competition/experiments/local_eval.py --execute
```

The default is two sequential runs, each with a 600-second readiness limit, 3600-second evaluation limit and bounded reporting/cleanup. At most five policies are permitted. The runner refuses execution if its conservative batch bound would pass **2026-11-03 07:30 UTC (08:30 Berlin)**. There is one nonblocking lock, a distinct container name, no host port publishing, `--pull=never`, and GPU access fixed by UUID via CDI (`--device nvidia.com/gpu=...`). Policies use an internal network (no egress), a 28 GiB RAM/no-swap cap and a bounded JAX memory fraction. `control/guard.py check` runs before engine access and before every policy run. Readiness uses namespace-local curl against the actual policy IP, requiring HTTP 200 and the endpoint contract (`alive_seconds` is a nonnegative integer or null). The simulator CLI and its descendants run in the same dedicated daemon network namespace, which can reach the policy internal network and download simulator assets; the policy container itself still has no egress. The record summarizer runs on the host. No requests are sent to host port 18080 or any unrelated service. Timeout, interrupt, failure and SIGTERM terminate the evaluation process group and remove only the runner's own named policy container. A hard machine kill still requires checking its recorded container name manually; no process can guarantee cleanup after SIGKILL.

## What is measured

The supported upstream command is `positronic eval run --eval=molmo.franka_pick_mini --policy=.remote ... --timing`, followed by `positronic eval timing-report --run_dir=...`. See `positronic/docs/local-molmospaces-eval.md`, `positronic/cli/eval/run.py`, and `positronic/cli/eval/timing_report.py` in the upstream checkout. There is no invented `--json` local eval flag and no platform submission flag.

The public mini suite has 20 episodes `[0..5,7..20]`; the smoke suite is `[0..4]`. The default harness runs the whole supported mini suite, verifies exact episode multiplicities and labels with upstream's integration checker, then reports development separately from the **15 held-out public-practice episodes `[5,7..20]`**. Use smoke to guide changes, freeze candidates before examining holdout results, and do not tune against holdout. These are public episodes, not the competition's private test set. Repeatedly choosing candidates from this holdout makes it validation data; do not claim an unbiased final estimate afterward.

Each unique results directory preserves logs, episodes, raw telemetry, upstream `timing_summary.json`, exact upstream success fractions in `metrics.json`, and batch `results.json`. Reported inference p50/p95 are upstream's **client-observed inference round trips across all selected episodes (5 for smoke, 20 for mini)**, including protocol overhead; they are not pure model compute time or heldout-only latency. Readiness/model loading is excluded from them. Keep episode coverage and `unscored` counts next to scores; incomplete runs fail validation and are never promoted. A failed baseline stops the batch. With only 15 holdout episodes, one success changes the rate by 6.7 percentage points, so small gains are uncertain.

The harness preserves the full timing report and per-episode records for later analysis. It does not establish determinism, run multi-seed trials, automatically promote a candidate, enforce competition VRAM limits, submit evaluations, prepare server dependencies, or schedule future GPU work. Verify upstream platform revision warnings before interpreting parity with official evaluation. A live GPU/server smoke run remains an integration prerequisite.

## Development screening and immutable local candidates

`eval` in the plan accepts only `molmo.franka_pick_mini_smoke` (5 development episodes) or `molmo.franka_pick_mini` (20 public validation episodes). `plan.json` keeps the 20-episode baseline control. Use `plan-smoke.json` for screening focused changes before examining holdout:

```sh
python3 competition/experiments/local_eval.py --config competition/experiments/plan-smoke.json
```

On the prepared server, pass the absolute task-root `experiments/plan-smoke.json` path with `--config` through the same watchdog launch command. Both sample plans repeat the baseline as a reproducibility control; neither represents a measured improvement. Replace only the candidate identity after preparing a distinct focused change.

Smoke metrics contain `development`, `full`, and the exact upstream development indices; they contain **no holdout score or holdout indices**. Mini metrics also contain the disjoint `holdout` score and indices. Coverage and split sizes are derived from the installed upstream public eval definitions and validated by its integration checker. Latency is written only after complete selected-suite coverage, a complete pass timing window, and positive inference-call count are validated. Missing/incomplete timing fails the run; a partial run does not produce comparable latency metrics.

Local plans also accept exact Docker config IDs `sha256:<64 lowercase hex>` to avoid publishing large experimental images. These are recorded as `identity_type: local-config-id`, distinct from `registry-manifest-digest` references of the form `registry/repo@sha256:<64 lowercase hex>`. A local config ID identifies the image in this dedicated engine and is not a published manifest digest. Official submissions still require a published manifest digest and separate approval.
