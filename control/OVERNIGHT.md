# Continuous Physical AI campaign controller

The user explicitly resumed on 3 November 2026 with **no time limit**, targeting **at least 50% official success**. The original overnight deadline is obsolete; `policy.json` now has `deadline: null`. The filename is retained for existing controller references. This is a research objective, not a promised score. Quota and manual-stop rules still apply.

The coordinator runs on this Mac with saved competition credentials. Up to two native workers use GPT-6.1 Sol medium for implementation and GPT-6 Luna medium for bounded analysis. No external coding-model helpers or paid API fallback. One GPU job runs at a time.

## Every wake and long turn

1. FIRST call live `get_usage_limits`. Prefer `rateLimitsByLimitId.codex`; remaining is `100-usedPercent` for every available primary/secondary window. Unknown usage, any stop marker, or <=25% remaining means stop workers and task GPU jobs, preserve evidence, delete the heartbeat and report. Preserve the user's 20% floor with the 25% buffer; never consume reset credits or use paid API fallback.
2. Immediately after **every live check**, including checks within long turns, feed its credential-free JSON `{collected_at, remaining_percent}` to `python3 control/save-usage.py` on the coordinator Mac. It atomically saves and mirrors the snapshot. Check at least every minute or four tool calls. The server watchdog stops jobs after seven minutes without a fresh snapshot. Do not delay mirroring until turn end. The helper never clears stop markers or starts services.
3. Read `AGENTS.md`, `control/policy.json`, this file and `EXPERIMENTS.md`; `control/read-context.py` displays changed text and confirms unchanged hashes. Read the latest experiment journal and live job state before deciding what to launch.
4. Continue real experiments: finish frozen MolmoAct2 vs baseline validation on fresh pick20 and the separate next-to placement10 diagnostic. Review exact outcomes and our own replays. Then explore alternative public policies (such as compatible GR00T), focused camera/action improvements and permitted fine-tuning. Declare development and untouched validation sets before outcomes; don't treat reused data as untouched. Keep controls and useful checkpoints.
5. Every long server job goes through `control/start-job.sh`. All code, models, datasets, caches, temporary files, logs and Docker state stay under `/opt/hderc-internal/nick/physical-ai-competition/`. Use only its dedicated rootless Docker via `docker/engine.sh`, the configured GPU UUID, one GPU job, and the disk reserve. Never modify shared Docker or production services. No paid cloud provisioning.
6. Record pinned images/source, settings, data provenance/splits, scores, unscored counts, latency and resources in `state/experiments.jsonl`. Coordinator alone appends this journal. Keep the best measured candidate; report uncertainty and placement/picking differences. Local success does not establish official >=50% success.
7. Official submissions remain approval-based. Approval so far covers only baseline digest `4359b618a74ebf38dfd548c25963ea781f967a9b34be8390ed5fa6e3128d7fda`. Prepare a tested pinned candidate and concrete comparison before asking the user to submit; do not consume another official submission automatically. Check current submission limits before any approved submission.
8. On quota/manual cutoff: interrupt workers, stop only task units with `control/guard.py stop`, write a handoff, delete the heartbeat and report. Do not clear later stop markers automatically. The user's explicit 3 November resume authorizes archiving only the prior stop marker and removing the obsolete deadline timer.

## Current official result

Baseline submission `6167d92cf2009b1e`: 62/320 successes (19.375%), zero unscored; rank20 when checked on 3 November. Stable public replay: https://app.positronic.ro/v/WKps7S_-qP89_bQ5kxbPhA/ . Public summary: `results/official-baseline-20261102.json`. The first horizon6 candidate tied baseline4/15 on held-out validation, so baseline was retained. MolmoAct2 scored4/5 vs baseline1/5 on development only and passed offline12-session tests; fresh validation is pending.

## Isolation and optional deadline

Owned user units: `nick-physical-ai-eval`, `nick-physical-ai-docker`, `nick-physical-ai-watchdog` and, only for an explicit future deadline, `nick-physical-ai-deadline`. No old 08:30 timer may remain armed for this resumed campaign. Keep individual job/request timeouts even with no campaign deadline.
