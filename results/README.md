# Local development screen — 2 November 2026

## Campaign resumed; fresh validation running

On 3 November the user explicitly resumed with no time deadline and a target of
at least 50% official success. The quota reserve remains. The fixed controller
is active and the fresh MolmoAct2 comparison is running; see [RESEARCH.md](../RESEARCH.md).

MolmoAct2 DROID completed **4/5 development tasks**, versus **1/5** for the repeated
baseline, with zero unscored episodes. Local inference p95 was 380.8 ms versus
68.0 ms. See [the development result](molmoact2-development-20261102.json).
This five-episode result is preliminary; fresh validation has not run, so the
approved baseline remains retained.

Previously, the watchdog stopped the campaign at 22:36:30 UTC when the coordinator failed to
mirror a usage refresh during a long turn. Allowance was still 63%. Task jobs
and engine were stopped, and the overnight automation was deleted. The refresh
path now mirrors every live check immediately. The user authorized restarting;
the new campaign automation is active. [HANDOFF.md](../HANDOFF.md) retains the history.

## Official baseline result

Team Nick's approved π0.5 DROID baseline finished the official
`molmo.competition_v2` evaluation at **19.375% success: 62/320 episodes**, with
zero unscored episodes. It ranked **20th when checked on 3 November**; rankings can change. The run ended at 22:20:06 UTC.
[Watch the stable public replay](https://app.positronic.ro/v/WKps7S_-qP89_bQ5kxbPhA/). See the [public competition leaderboard](https://competition.phail.ai/)
and [saved result summary](official-baseline-20261102.json).
The local practice experiments below use a different task set and are separate
from this official result. No additional official submission has been made.

## Validation outcome: retain baseline

The frozen 6/15 s candidate **did not improve held-out success**:

| Policy | Development | Held-out validation | Total |
| --- | ---: | ---: | ---: |
| Baseline 8/15 s | 1/5 | 4/15 | 5/20 |
| Candidate 6/15 s | 3/5 | 4/15 | 7/20 |

All 40 episodes were scored. On the 15 held-out episodes, three improved and
three regressed; one succeeded for both policies and eight failed for both.
The paired net gain was zero (exact two-sided McNemar p=1.0). Each policy's
success interval is wide (Wilson 95%: 10.9–52.0%), so this small comparison does
not establish superiority or equivalence. Keep the approved baseline.

Task instructions and shoulder-slot side metadata matched for every pair.
Matching all simulator randomness has not been established. Inference p95 was
69.1 ms baseline and 69.8 ms candidate; observed maxima were 100.4 and 99.9 ms.
See [validation results](horizon-validation-20261102.json) and
[paired episode analysis](horizon-paired-validation-20261102.json).
Multi-session reliability qualification completed separately; no additional
official submission has been made.

## Offline runtime qualification

The unchanged baseline and public MolmoAct2 DROID image both passed 2-session
and 12-session checks, including distinct server IDs, valid commands and
acknowledged close/reopen. Each 12-session check used two waves and 48 inference
calls under denied egress.

| Policy | 12-session p95 | Observed maximum | Sampled GPU card peak |
| --- | ---: | ---: | ---: |
| π0.5 baseline | 0.738 s | 0.739 s | 8,932 MiB |
| MolmoAct2 DROID | 4.433 s | 4.447 s | 12,738 MiB |

These local round trips include queueing; the samples are below 15 seconds.
Card-memory sampling can miss short peaks and includes any other card users.
This does not reproduce the competition GPU or establish task-score gains.
MolmoAct2 emits slightly negative initial gripper predictions; the existing
simulator actuator clips finite grip to [0,1]. That behavior was preserved and
recorded, with no image change. See the
[runtime summary](runtime-qualification-20261102.json).

## Earlier development screen

The five development episodes were identical across policies; all were scored.

| Policy | Successes | Inference p95 | Total episode wall time |
| --- | ---: | ---: | ---: |
| Baseline, 8/15 s horizon | 0/5 | 69.3 ms | 180.1 s |
| 6/15 s horizon | 2/5 | 69.7 ms | 137.9 s |
| 10/15 s horizon | 2/5 | 69.2 ms | 159.7 s |

Only the action horizon changed. Both variants picked up the tissue box and
tissue in episodes 3 and 4; kettle, remote and ladle episodes remained failures.
The five-episode development sample is too small to establish a general gain.
Inference figures cover recorded W_pass calls on the local RTX PRO 6000,
including each episode's first call; server startup before the pass is excluded.
The closed-span audit found maxima of 100.6, 122.6 and 97.8 ms respectively.
This establishes observed local latency for one session at a time, not a
competition timing guarantee or multi-session qualification. See the
[latency audit](horizon-development-latency-20261102.json); its first-call
exclusion is an operational label, not a measurement of compiler warmup.

The 6/15 s candidate was frozen for a paired 20-episode validation against the
baseline, with 15 previously unused episodes reported separately above. The two
development candidates tied; the shorter candidate was first in the planned
sweep and completed its development batch faster. It has not been promoted or
submitted to the competition.

These are **local public-practice** results, using Positronic commit
`00fdd933f22158a9cbe6d97c5b19c2935df35c1b` and MolmoSpaces commit `713fd12`.
The local adapter revision differs from the public practice catalog's pinned
revision, including camera/task handling. These numbers are an internal paired
comparison, not official competition scores or a prediction of them. The hidden
competition evaluator's revision has not been established.

Exact image identities, counts and timings are in
[horizon-development-20261102.json](horizon-development-20261102.json).
Candidate identities beginning with bare `sha256:` are local image config IDs,
not registry manifest digests. A future submission must use a published manifest
digest and requires human approval. The approved baseline submission
`6167d92cf2009b1e` completed with the official result above.

Private raw recordings remain in the task folder. No other team's data was used.
