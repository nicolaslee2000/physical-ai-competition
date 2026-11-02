# Overnight experiment controller

Authorized run: 2–3 November 2026, ending **3 November 08:30 Europe/Berlin (07:30 UTC)**. Optimize the measured policy before this deadline; no fixed success score is promised. `policy.json` and root `AGENTS.md` govern every wake and worker.

The existing chat heartbeat `watch-physical-ai-baseline-evaluation` is extended into the controller. The coordinator runs on this Mac using native Codex tools and saved local competition credentials. Two workers may operate in parallel on disjoint files: GPT-6.1 Sol medium for implementation, GPT-6 Luna medium for bounded analysis. One GPU job at a time keeps comparisons interpretable. The native allowance is shared across the account; model API prices do not directly specify its percentage consumption.

## Every wake

1. Read live account usage with the Codex app `get_usage_limits` tool. Prefer `rateLimitsByLimitId.codex`; inspect all primary/secondary windows. Compute remaining as `100-usedPercent`. Unknown usage, a stop marker, 25% remaining or less, or the deadline means stop research and workers. Never consume a reset or switch to paid API billing. Check again before/after meaningful work and within long worker turns.
2. If allowed, atomically write `state/usage.json` containing Unix `collected_at` and a `remaining_percent` list. Mirror to the server at the same task-relative location, using a temporary `.new` file then rename. The watchdog stops jobs if the snapshot is more than seven minutes old. This also stops GPU work when the Mac becomes unavailable; it is deliberately fail-closed.
3. Read baseline submission `6167d92cf2009b1e` without printing the API key. Save completed results and stable replay/report links. Signed artifact URLs and secrets do not belong in the public repository. If still evaluating, continue independent local harness setup rather than repeatedly calling the platform.
4. Read `EXPERIMENTS.md` and existing experiment records. Prepare the supported local simulator under the task root, run a baseline smoke test, then baseline validation, then one focused candidate at a time. Inspect actual replay/log evidence. Keep development and holdout episodes separate. A smoke or readiness check cannot establish improvement.
5. Use `control/start-job.sh COMMAND ...` for every long server job, including dependency setup and asset downloads. Use `docker/engine.sh` for Docker and start the dedicated rootless engine only after a successful `control/guard.py check`. Cache/source/environment/temp/model/output paths all remain in the server task root. Respect physical disk headroom and production services. The GPU has been cleared by the user and can be used for authorized experiments; never stop other services or change shared Docker.
6. Record the hypothesis, source commit, pinned image, data split, success counts, latency, errors, and whether the candidate beat the control. Preserve the best verified checkpoint. Prepare improved images for review; additional official submissions still require explicit approval.
7. On quota cutoff, unavailable usage, a manual stop or deadline: interrupt workers, mirror the stop marker, run `python3 control/guard.py stop` on the server, preserve results, write a concise handoff, delete the overnight heartbeat, and report the evidence. The server deadline timer independently stops task units at 08:29:30 Berlin, allowing shutdown before 08:30. Do not silently extend or resume the campaign.

## Resource and shutdown boundaries

All server state is under `/opt/hderc-internal/nick/physical-ai-competition/`. Task-owned user units are `nick-physical-ai-docker`, `nick-physical-ai-eval`, `nick-physical-ai-watchdog`, and `nick-physical-ai-deadline`. The shared production Docker engine is never used. The watchdog and timer are transient OS scheduling metadata; their scripts/logs/model files are within the task directory.

The guard also preserves at least 60 GiB of free filesystem space. Initial dependencies are prepared by `control/bootstrap.sh`; `control/probe-network.sh` verifies rootless internal-network namespace connectivity and denied egress without loading the model.

25% is a conservative stop threshold protecting the requested 20% reserve. There is no transactional account-wide percentage cap: usage can update late and other chats share it. Bounded workers and repeated live checks reduce the chance of crossing the reserve; an exact cutoff cannot be guaranteed.
