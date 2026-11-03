**Independent Astra review completed; research resumed 3 November.** Follow
`ASTRA-REVIEW.md` for the current ranked plan and validation gates. The matching
handoff pause was archived under the explicit resume authorization. Earlier
pending/paused statements below are historical. MolmoBot runtime viability is
next; stock MolmoAct2 is the local control; graph/GR00T holdouts stay unused.
Any later stop remains binding. Official submission still requires approval.

# Physical AI research campaign

**Paused for fresh Astra Max review at the user's request.** Current prompt
stress completed. Both policies passed the functional checks, but varied-prompt
12-session maximum latency was12.388s graph vs4.504s stock, reversing the
same-prompt speed advantage. Sampled card totals were14.40GB vs13.40GB; true
peak remains unknown. See results/molmo-graph-prompt-stress-20261103.json.
Task job/engine/watchdog are stopped and the old heartbeat is deleted. New
experiments resume only after the fresh chat's independent review and plan.

**Resumed 3 November:** the user removed the deadline, requested multiple models
and methods including public datasets, and set an official success target of
at least 50%. Quota stop25%/user reserve20%, storage isolation and submission
approvals remain unchanged. The prior stop was explicitly rearmed. The fresh
pick20 MolmoAct2 comparison completed: **8/20 vs baseline4/20**, zero unscored,
six improved/two regressed, exact McNemar p=0.289. This is a small local picking
sample and does not establish the official target. Placement10 completed in
`fresh-20261103T094610Z-1b8b2137`: **MolmoAct2 4/10 vs baseline2/10**, zero
unscored; two improved, none regressed (exact McNemar p=0.5). Both cohorts are
consumed; do not reuse them as untouched validation. MolmoAct2 remains the best
measured local candidate, with no new official submission.
GR00T passed offline2/12session checks but scored **1/5 development vs baseline3/5**.
Do not consume its untouched fresh cohort without a new development rationale.
The baseline has varied between small reruns; avoid cross-batch causal rankings.
A MolmoAct2 CUDA-graph image scored **5/5 development vs stock MolmoAct2 2/5**.
Median inference was163ms vs371ms; graph p95 was1026ms due to capture overhead.
Same-prompt12session checks passed, but varied-prompt memory/concurrent recapture
checks are pending. The graph pick20 cohort is frozen and unused; do not launch
it before those gates. See results/molmo-graph-development-20261103.json.
MolmoBot-DROID has a mocked native adapter and offline packaging draft. Its
pinned base and all six public20GB artifacts are downloaded and hash-verified;
dependency resolution, actual memory and model tests remain pending.
See `RESEARCH.md` and `results/molmoact2-fresh-pick-20261103.json`.
The cohort cache-location typo was corrected after checking both actual manifest
hashes; indices, seeds and source contents did not change. Current cohort SHA:
pick `d31b93cf300e347b86323cf42bf16aaca6ac016b532e7ca5140eeec34414231d`,
placement `3f95af6784d3b25d5988a69db2e8f563dbed4af64ee0e340a02078faccb9920b`.

## Baseline and guardrails

Keep the official π0.5 DROID image as the control: base image pinned in `Dockerfile`; submitted digest `ghcr.io/nicolaslee2000/physical-ai-competition@sha256:4359b618a74ebf38dfd548c25963ea781f967a9b34be8390ed5fa6e3128d7fda`. Submission `6167d92cf2009b1e` finished successfully: **62/320 successes (19.375%)**, zero unscored, ranked 19 when checked at 22:23 UTC. Stable replay: https://app.positronic.ro/v/WKps7S_-qP89_bQ5kxbPhA/. `results/official-baseline-20261102.json` records the result. `validation.json` only establishes the earlier offline startup/readiness check; scored evidence is separate.

Constraints from the competition guide: the runtime has no network, gets one 24 GB GPU slice, and opens one server session per episode. The local GPU is useful for controlled comparisons, but cannot reproduce competition hardware exactly. Before testing variants, preserve the baseline image/digest and its result artifacts; package all candidate dependencies and weights offline. Official submissions remain approval-based; verify the current competition quota before any submission.

## Run plan

For every candidate: change one knob, build a distinct image, run offline startup, then evaluate the same task/seed set and report successful episodes / attempted episodes, primary score, unscored and failure counts, and inference latency p50/p95/max. Include first inference separately (warmup/compile); record per-episode wall time. Paired seeds make the baseline comparison interpretable. Tune on a development slice; reserve a disjoint, untouched holdout (balanced across task families and left/right shoulder views) for the final check. Do not repeatedly tune against leaderboard scores. Promote only if holdout success improves without latency, crash, memory, or startup regressions; otherwise retain baseline.

### 1. Shoulder-view robustness — first priority, low code risk

- **Evidence:** `positronic/positronic/vendors/openpi/codecs.py` maps the DROID `EXTERIOR_IMAGE_LEFT` input to the single `keys.EXTERIOR_IMAGE` signal; `positronic/positronic/simulator/robolab/keys.py` defines distinct over-shoulder left and right views and camera layouts. This makes the chosen shoulder view a concrete distribution-mismatch hypothesis, not a known defect.
- **Experiment:** compare the current left-view mapping against right-view mapping, one at a time, on identical development episodes; stratify results by view side and task. Keep the wrist input, checkpoint, prompt, image size, and action schedule fixed. If the eval supplies randomized shoulder views within a run, include both sides in each comparison and confirm the mapping remains consistent per episode. Do not swap or randomize camera tensor slots at inference without matching the trained input semantics.
- **Measure / gate:** per-side success, overall primary score, and latency. Test a view-specific mapping only if episode metadata supports choosing the correct view; otherwise do not add a brittle heuristic. Recheck on held-out seeds and both views.

### 2. Replanning cadence — bounded schedule sweep

- **Evidence:** `positronic/positronic/vendors/openpi/server.py` binds `droid_pipe` to `horizon_sec=8/15`; `ChunkedSchedule(fps, horizon_sec)` governs chunk scheduling. `positronic/offboard/README.md` documents per-session pipeline overrides; the DROID codec README describes an 8-step open-loop chunk. At 15 fps the baseline horizon is 0.533 s.
- **Experiment:** compare baseline 8/15 s with modest shorter and longer horizons (e.g. 6/15 and 10/15 s), holding checkpoint, camera mapping, and all decoding constant. Prefer session overrides for local screening if accepted by the evaluator; otherwise patch only this pipeline default in a separately tagged candidate. Capture both inference latency and number of replans/episode (expected roughly episode frames divided by horizon frames; record actual counts).
- **Measure / gate:** primary success and per-inference p95/max, failures, and episode duration. Shorter horizons increase replanning calls; longer horizons reduce correction opportunities. The code establishes the knob, not which setting improves score. Retain baseline unless held-out paired results support a change and timing remains within evaluator limits.

### 3. Multi-session correctness and resource headroom — qualification, not score tuning

- **Evidence:** the competition opens a WebSocket session per episode. `positronic/offboard/server.py` makes session IDs per connection and serializes model calls under `_infer_lock`; `openpi/server.py` forwards the session ID to its shared model. This serializes backend inference even when episodes connect concurrently.
- **Experiment:** offline smoke test two or more simultaneous sessions through the production image, verify each receives valid chunks and reset/end-session behavior, and measure queue wait plus inference latency under concurrency. Check peak GPU memory and container RAM at the configured 28 GiB local cap; actual competition GPU memory is 24 GB. Confirm no first-session-only cache or cross-session state leak.
- **Measure / gate:** all sessions complete, outputs stay attributable to their session, p95/max latency and memory remain safe. This is a reliability check; do not claim task-score gains from it. If timing fails, profile before changing the model or image.

## Order and stop rule

1. Read submission status/artifacts when available and record baseline score, episode counts, latency, and failures.
2. Screen camera mapping, then schedule cadence; each screen uses paired development episodes and one-knob changes. Run multi-session qualification once against the baseline and any finalist.
3. Evaluate only the finalist on untouched holdout seeds, balanced across shoulder sides. Preserve logs, image digest, exact setting, sample counts, and metrics.
4. If no candidate clears the holdout gate before the deadline, keep the pinned baseline. A readiness pass alone is not evidence for a policy improvement.

## Measured progress and next model screen

The first local development screen completed: baseline 0/5, horizon 6/15 and
10/15 both 2/5, with no unscored episodes. The 6/15 candidate was frozen before
the paired 20-episode validation began. Its 15 non-development episodes remain
separate from tuning. The baseline repeat scored 5/20 and the candidate 7/20,
but both scored **4/15 on held-out validation** (three improved, three regressed).
The baseline is retained; there is no held-out gain. Baseline development performance
also varied between runs, reinforcing the need to report uncertainty.
See `results/README.md` for exact identities, latency and revision limitations.

Baseline and MolmoAct2 both passed offline session lifecycle checks with 2 then
12 sessions. At 12 sessions, maxima were 0.739 s and 4.447 s respectively; sampled
card memory stayed below 13 GiB. See `results/runtime-qualification-20261102.json`.
These are local reliability observations, not official hardware guarantees.

The official public MolmoAct2 DROID example scored **4/5 development successes**
versus the repeated baseline's **1/5**, using `experiments/plan-molmoact2-smoke.json`.
Fresh pick validation scored8/20 vs baseline4/20; placement assessment is pending.
This does not yet establish an official improvement. This tests a
different pretrained policy, not another action-horizon adjustment. The official
recipe's `droid_3cam` default consumes both exterior slots plus wrist, which the
current local adapter supplies. Keep all model defaults unchanged. Pull only
after the current GPU comparison/qualification has ended, through the dedicated
engine and guarded job controller, preserving at least 60 GiB free disk.
The source/model and memory evidence is in the official
[image guide](https://github.com/Positronic-Robotics/positronic/blob/00fdd933f22158a9cbe6d97c5b19c2935df35c1b/docs/submit-a-policy-image.md).

Do not reuse the first candidate's validation split as an untouched holdout for
later tuning or candidates. Further validation requires a newly frozen public
episode set and transparent provenance, or must be labelled exploratory.
The official leaderboard remains separate and approval-based.

## Stopped at 22:36 UTC

The watchdog stopped the campaign because the coordinator failed to mirror its
live usage checks during a long turn; the last server snapshot expired. Usage
still had 63% remaining. Task jobs/engine are stopped and the overnight heartbeat
was deleted. `control/save-usage.py` now mirrors each live check immediately,
without clearing stop markers. `HANDOFF.md` records the prepared fresh pick20 and
placement10 tests. Respect the stop latch; do not rearm without explicit resume.

## 3 November, 09:46 UTC: placement comparison resumed

The campaign remains active with no time limit following the explicit resume.
The historical 22:36 stop above was resolved by that resume; quota snapshots now
mirror immediately. All 385 frozen-scene object dependencies are ready. The
unchanged placement10 comparison restarted in batch
`fresh-20261103T094610Z-1b8b2137`; scores are pending. GR00T is cached and its
development/session screen is next. Public demo conversion remains prepared,
not executed. No additional official submission has been made.
