# Overnight experiment backlog (Nov 2–3)

## Baseline and guardrails

Keep the official π0.5 DROID image as the control: base image pinned in `Dockerfile`; submitted digest `ghcr.io/nicolaslee2000/physical-ai-competition@sha256:4359b618a74ebf38dfd548c25963ea781f967a9b34be8390ed5fa6e3128d7fda` (submission `6167d92cf2009b1e` is still evaluating). `validation.json` establishes offline startup/readiness only (51 s); it explicitly does not establish task success or inference latency. Do not interpret a candidate as better without scored task outcomes.

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
