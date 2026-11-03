**Independent Astra review completed; research resumed 3 November.** Follow
`ASTRA-REVIEW.md` for the current ranked plan and validation gates. The matching
handoff pause was archived under the explicit resume authorization. Earlier
pending/paused statements below are historical. MolmoBot runtime viability is
next; stock MolmoAct2 is the local control; graph/GR00T holdouts stay unused.
Any later stop remains binding. Official submission still requires approval.

# Physical AI improvement campaign

**User-requested Astra Max review transition (3 November):** the current prompt
stress job finished; task GPU job, engine and watchdog are stopped and the old
heartbeat was deleted. Read `state/astra-review-handoff.json` and
`state/astra-review-authorization-20261103.json`. The new Astra Max chat must
independently audit and replan before resuming. The same human instruction
authorizes resume after that review, including archiving ONLY the matching
handoff stop marker whose SHA is recorded in the authorization. Any different
or later manual/quota stop remains binding. No new experiment before review.

Read `control/policy.json`, `state/usage.json`, `EXPERIMENTS.md`, and this file before doing research. On 3 November the user explicitly resumed the campaign with **no time limit**, targeting at least **50% official competition success**. `deadline: null` is intentional. The quota reserve, stop markers, storage isolation and submission approvals remain binding. A local success rate does not establish the official target.

- Before every meaningful action and before spawning a worker, call the Codex app `get_usage_limits` tool. Prefer the `codex` entry in `rateLimitsByLimitId`; use all available primary/secondary windows. Remaining percent is `100 - usedPercent`. Missing quota data fails closed. Never consume reset credits or use paid API fallback.
- Stop launching work at 25% remaining, leaving a buffer above the user's 20% floor. Interrupt active workers and stop task GPU jobs when the threshold is reached. Check usage within long agent turns, at least once per minute or every four tool calls. Account usage is shared and delayed; an exact 20% hard cap cannot be guaranteed.
- Immediately after EVERY live usage check, including checks inside long turns, feed the credential-free `{collected_at, remaining_percent}` snapshot to `python3 control/save-usage.py` on stdin. It atomically saves and mirrors it. Do not defer mirroring until the next heartbeat or turn end. Snapshots expire after seven minutes; the server watchdog then stops task-owned jobs. Respect `state/STOP` and `state/stopped.json`; do not clear stop markers automatically. The previous campaign stopped after a long turn refreshed live usage but failed to mirror it promptly.
- At most TWO worker agents in addition to the coordinator. Use native Codex collaboration tools only: GPT-6.1 Sol at medium reasoning for implementation/complex analysis, GPT-6 Luna at medium for bounded log triage/documentation. No recursive workers or external coding helpers. Do not spawn agents just to wait on jobs. Keep handoffs concise and file ownership disjoint.
- Give workers bounded tasks (roughly 4,000–6,000 tokens of work), require usage checks within the turn, and interrupt them on quota/manual cutoff. If a future explicit deadline is configured, do not open new worker tasks in its final 15 minutes. No worker may extend a deadline or remove a stop marker on its own.
- All server code, models, datasets, caches, temp files, Docker data and logs must remain under `/opt/hderc-internal/nick/physical-ai-competition/`. Use only its dedicated rootless Docker engine through `docker/engine.sh`. Never touch shared Docker, production services, or the resident LLM. Use the free GPU headroom; do not unload production models.
- Run at most one GPU experiment at a time. Launch long jobs ONLY through `control/start-job.sh` so the watchdog can stop them. Recheck the guard before starting the task engine. Preserve completed checkpoints/results. No paid cloud provisioning is authorized. A deadline timer exists only when the policy contains an explicit deadline.
- Use simulator task success and measured latency as evidence. Read our own result artifacts and replay, identify one failure mode, make one focused change, and compare on development episodes. Keep held-out episodes separate; record their provenance. Never claim improvement from readiness tests or invented scores. Do not train on other teams' evaluation data or exploit simulator/scoring internals.
- Explore distinct methods deliberately: alternative compatible pretrained policies, camera/input and action-execution improvements, and fine-tuning on permitted public demonstrations or our own data. Keep each hypothesis and its cost bounded, compare against control, and avoid repeatedly tuning against consumed holdouts. Placement and picking both matter to the official task mixture.
- Keep the known baseline and record every experiment's commit, settings, dataset split, success counts, latency and resource use in `state/experiments.jsonl`. Avoid simultaneous writes from workers. Do not overwrite a better checkpoint with an unmeasured candidate.
- Official submissions remain approval-based. The previous approval applied to baseline digest `4359b618a74ebf38dfd548c25963ea781f967a9b34be8390ed5fa6e3128d7fda` only. Prepare and validate improved candidates for review, but do not consume additional official submissions automatically. Verify current competition limits before any approved submission.
- Notify only meaningful improvements, failures, blockers, the deadline or reserve cutoff. Stay quiet while results are unchanged. At cutoff, stop task GPU jobs/engine, interrupt workers, save a handoff and best evidence, remove the overnight heartbeat, and report what actually ran.
