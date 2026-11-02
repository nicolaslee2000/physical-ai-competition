# Local development screen — 2 November 2026

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
Multi-session reliability qualification is running separately; no additional
official submission has been made.

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
`6167d92cf2009b1e` remains in the evaluating stage as of 21:47 UTC.

Private raw recordings remain in the task folder. No other team's data was used.
