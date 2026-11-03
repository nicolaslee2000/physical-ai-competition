# Physical AI improvement campaign

User-authorized on 3 November 2026: continue without a time deadline, explore
different models and methods, and target **at least 50% official success**.
The current official score is 19.375% (62/320). The target is not yet achieved.
Usage stops at 25% remaining to protect the user's 20% reserve. GPU use is
authorized within the isolated server folder; official submissions need approval.

## Active sequence

1. **MolmoAct2 validation completed:** fresh pick8/20 vs baseline4/20; separate
   placement4/10 vs2/10, zero unscored. Both small cohorts are consumed and remain
   separate from training. These results do not establish the official target.
2. **GR00T N1.7 DROID screening active:** the pinned image is cached. The guarded
   control/run-groot-screen.sh performs offline2/12session qualification then the
   same development0..4 comparison. The disjoint fresh-groot-pick-cohort.json is
   frozen for a finalist after development decisions. A simulation-trained
   MolmoBot-DROID adapter is also undergoing source/client compatibility review;
   it has not been built or evaluated. Preserve per-session history and native
   protocol compatibility; do not assume custom client code ships with an image.
3. **Audit public training data:** inspect metadata, terms, success labels,
   embodiment, cameras, frame conventions and action units before training.
   Candidate sources are the official ten MolmoSpaces demos, the separate
   214-episode simulator pick/place dataset, and OpenPI's small successful DROID
   sample. Public availability alone does not establish license or compatibility.
   Full DROID (terabyte scale) is not the initial experiment.
4. **Focused policy improvements:** inspect our own failures, then test one
   camera/input robustness or action-execution change at a time. Use the actual
   production observation contract; no simulator internals at inference.
5. **Fine-tune a compatible baseline:** begin with a bounded pipeline pilot,
   then a justified training run on permitted successful demonstrations. Maintain
   separate dataset-development IDs and untouched evaluation IDs, preserve
   provenance/attribution, and compare against the original checkpoint. The ten
   example demos are a pipeline check; their publisher does not promise gains.

## Promotion and approval

Keep each hypothesis and experiment bounded even though the overall campaign has
no deadline. Retain the best supported checkpoint. The official task mixture
includes placement, so success on picking alone cannot substantiate the 50% goal.
Use local tests to prepare a concrete candidate, with denied-network startup,
24 GB inference headroom and 12-session timing checks. Ask for approval only when
an exact digest and reviewable evidence are ready. Do not consume submissions
automatically or claim official improvement from local practice.

## Public data sources

- [Positronic public simulator dataset configurations](https://github.com/Positronic-Robotics/positronic/blob/main/positronic/cfg/ds/sim.py)
- [Official competition fine-tuning example](https://github.com/Positronic-Robotics/positronic/blob/main/docs/nebius-competition.md#fine-tune-gr00t-on-demonstrations)
- [OpenPI DROID training guide](https://github.com/Physical-Intelligence/openpi/blob/main/examples/droid/README_train.md)

Private audit findings live in `state/alternative-model-plan.md` and
`state/public-data-audit.md` when available. `AGENTS.md`, `control/policy.json`,
`control/OVERNIGHT.md` and the append-only experiment journal govern execution.
