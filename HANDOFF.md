# Campaign stopped — 2 November, 22:36 UTC

The server watchdog latched a stop at **22:36:30 UTC** because its usage snapshot
expired. The coordinator continued checking live Codex usage but failed to mirror
those checks during a long turn. Live allowance was still **63% remaining**.
This was a controller error, not quota exhaustion or a user-requested stop.

All task GPU jobs, the dedicated rootless Docker engine and watchdog are stopped.
Both native workers completed and are idle. The overnight heartbeat was deleted.
Production services were not changed. Model images and results remain under
`/opt/hderc-internal/nick/physical-ai-competition/`.

## Results retained

- **Official approved π0.5 baseline:** 62/320 successes, **19.375%**, zero unscored;
  ranked 19 when checked. Submission `6167d92cf2009b1e`. Stable replay/report still
  pending publication. See `results/official-baseline-20261102.json`.
- Horizon 6/15 candidate: tied baseline **4/15** on the first held-out validation;
  not promoted. Its overall 7/20 versus 5/20 included development episodes.
- **MolmoAct2 DROID development screen:** **4/5** versus repeated baseline **1/5**,
  zero unscored. This is promising development evidence, not held-out improvement.
  See `results/molmoact2-development-20261102.json`.
- Both unchanged images passed offline 2- and 12-session lifecycle checks. At
  12 sessions, observed inference maxima were 0.739 s baseline and 4.447 s
  MolmoAct2; sampled GPU card peaks were 8,932 and 12,738 MiB. Local hardware
  observations do not guarantee competition hardware behavior.

No additional official submission was made. The approved baseline remains the
retained official image; MolmoAct2 has not been promoted on development scores.

## Prepared next steps, requiring explicit resume

1. Preserve the stop marker until the user authorizes resuming. The user required
   automatic stopping on any marker, so the coordinator must not rearm silently.
2. Use `control/save-usage.py` on the coordinator Mac **immediately after every
   live usage check**. Its live-snapshot validation and actual atomic server
   mirroring were checked while stopped; it does not clear markers or start jobs.
3. Resume only within the original deadline: **3 November 08:30 Berlin / 07:30 UTC**,
   stop at 25% remaining, never reset credits or switch to paid API usage.
4. Run frozen MolmoAct2 versus baseline fresh public validation: 20 pick episodes,
   then the separate 10-episode next-to placement diagnostic. Both cohorts were
   frozen before MolmoAct2 task outcomes; neither has been run. The placement
   cohort has no curated right-view visibility list, which must be reported.
5. Use `experiments/fresh_eval.py`, exact cohort SHA, the upstream blocklist and
   `experiments/plan-molmoact2-fresh.json`, always through `control/start-job.sh`.
   The runner has seven offline tests; live custom-cohort integration is untested.
6. Inspect paired outcomes and replays, retain the best supported policy, and
   prepare a registry image for review. Further official submissions still need
   explicit human approval. Retrieve the official stable replay link when ready.

MolmoAct2 image:
`positro/molmoact2-droid@sha256:53be1ce8e9c6456626987720b08d713fa6d2c62eb4b4b9338393d5e4e35802b6`.
All images have been pulled; no new model download is needed for these tests.

Private detailed evidence and the append-only experiment ledger are in `state/`.
