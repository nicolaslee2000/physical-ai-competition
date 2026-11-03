# Independent review and revised research plan — 3 November 2026

Reviewed by the new coordinator before restarting the task engine or any experiment.
The objective remains **at least 50% measured official success**. There is no
campaign deadline. This is a research target, not an achieved result or forecast.
The only official result is **62/320 (19.375%)**, submission `6167d92cf2009b1e`.
No additional official submission is authorized.

## What the evidence supports

I independently recounted the saved per-episode pick and placement records,
checked the corresponding server result files, inspected recording clock flags,
read the pinned model/evaluator source, and checked the current public rules.

| Evidence | Verified result | Interpretation |
|---|---|---|
| Fresh local pick20 | Stock MolmoAct2 8/20, pi0.5 4/20; 6 gains, 2 losses | Best current local lead; small, consumed sample; exact paired p=.289 |
| Fresh next-to10 | Stock MolmoAct2 4/10, pi0.5 2/10; 2 gains, 0 losses | Small, consumed diagnostic; p=.5; does not test in/on placement |
| Graph development5 | Graph 5/5, stock MolmoAct2 2/5 | Reused development; no generalization claim |
| Mixed-prompt12 | Graph max12.388s, stock4.504s | Graph recapture loses the same-prompt speed benefit; both functionally pass |
| GR00T development5 | GR00T1/5, contemporary pi0.5 3/5 | Deprioritize unchanged checkpoint; fresh20 remains unused |
| MolmoBot | Pinned source, adapter tests and verified20GB artifacts | Prepared, not a runnable or measured policy yet |

Raw inputs: `state/fresh-pick-20261103/{baseline,molmoact2}.json`,
`state/fresh-placement-20261103/{baseline,molmoact2}.json`,
`state/molmo-graph-development-20261103/results.json`,
`state/molmo-prompt-sweep-20261103/results.json`, and
`state/official-baseline/result.json`. Public summaries are in `results/`.
The corresponding server batches are `fresh-20261103T082057Z-2d36cbd4`,
`fresh-20261103T094610Z-1b8b2137`, `20261103T103720Z-b729040a`, and
`qualification-20261103T110105Z-31b37297`.

### Assumptions that must change

1. **Our task mix misses the largest placement category.** Recounting our own
   official instruction aggregates gives pick49/176, in/on12/128 and next-to1/16.
   This is a text-based descriptive grouping, not a causal grasp-stage diagnosis.
   In/on accounts for40% of that run, versus5% next-to. A pick-focused programme
   and next-to-only placement diagnostic cannot substantiate the50% objective.
2. **Local trials already charge thinking time**, confirmed in all70 recordings
   of the pick20, placement10 and graph5 comparisons. The concern is different
   hardware/load, not an uncharged simulator. The official guide specifies a
   quarter-compute24GB slice and up to12 sessions; our full card and4CPU local
   cap are not equivalent. Neither a simple4x slowdown nor official12-way
   overlap is measured. Treat those as sensitivity scenarios, not predictions.
3. **Matched environment seeds are not matched model noise.** Pinned MolmoAct2
   `predict_action` samples `torch.randn(..., generator=generator)`, while the
   shipped policy supplies no generator. Its graph receives the sampled
   trajectory as an input. Repeated stock results vary. Graph5/5 therefore does
   not identify either an action-quality gain or a speed-caused success gain.
4. **The current graph is not a safe finalist.** Pinned `ActionCudaGraphManager`
   has one shape-keyed slot, overwritten on shape changes. Unpadded prompts
   change KV shapes. The measured varied-prompt regression is consistent with
   recapture, but capture counts and allocated/reserved peaks were not measured.
   Sparse card samples cannot certify transient memory or24GB compliance.
5. **MolmoBot is promising because of training-domain fit, not because files
   exist.** Its official training recipe includes Franka pick, in/on, color and
   next-to data with random exterior views. The reviewed loader and adapter still
   need dependency, memory, timing and native protocol proof. Its one-action RPC
   design can create severe load and timing/history differences. Do not assume
   the eight mocked tests close those gaps.
6. **Ten demonstrations are a conversion check.** They do not justify a costly
   fine-tune or an expected gain. Dataset size on disk is also not inference VRAM.
   The official evaluator/client revision remains unresolved: the public practice
   revision is not proof of the competition revision. Live catalog exposes the
   competition id but no revision. Keep this limitation explicit.

## Ranked directions and bounded next experiments

### 1. MolmoBot-DROID viability, then representative task screening

This is the strongest distinct policy hypothesis. Reuse the already verified
weights and pinned source; do not download another checkpoint or a large dataset.

**Immediate iteration:** at most45minutes for isolated dependency resolution,
hash-lock/wheelhouse, notices and CPU import checks. Use the cached pinned
PyTorch2.8/CUDA12.8/Python3.11 base. Keep the active evaluator environments intact.
Resolve serving dependencies without installing the upstream simulator eval
extra. Do not weaken provenance or alter model mathematics to bypass a resolver.
Preserve the lock/failure evidence; after two clearly diagnosed compatibility
repairs, reconsider this route before further package work.

Then run a maximum15minute offline one-process load/inference probe with mounted
verified artifacts before duplicating the weights into a distributable image.
Measure load wall time, cgroup peak host memory, CUDA allocated/reserved peaks,
process/card samples, first inference, steady p50/p95/max, two and four image
history cases, output shape/finiteness and offline tokenizer initialization.
Keep host RAM<=28GiB and policy GPU peaks below22GB with explicit untracked-driver
headroom; any OOM or missing peak evidence blocks qualification. Disk free must
remain above60GiB, including staging/build expansion. No shared GPU reconfiguration.

If viable, package the exact runtime, then test1/2/12 sessions, alternating real
development prompts, cold/reopen/reset isolation, delivered control cadence and
history timestamps. Record per-RPC queue time separately from generation time.
Any >=15s call, state leak, history-contract failure or memory breach rejects the
current adapter. Target <10s full-card mixed12 maximum as a local margin, while
explicitly retaining quarter-slice uncertainty. Profile before changing the
one-action adapter; do not silently remove its per-step clamp or temporal context.

Only after those gates: paired development against stock MolmoAct2, with pi0.5 as
an anchor. Use5 consumed picking cases,5 consumed next-to cases, and6 predeclared
new in/on development cases. Run two independently seeded blocks, reverse policy
order in block2, balance shoulder order, and log environment and policy RNG
seeds separately. Require a repeatable net gain with no task-family collapse to
spend untouched validation. A few successes alone are not promotion.

### 2. Stock MolmoAct2 robustness and timing controls

Keep it as the best measured local control. On consumed development observations,
add a fixed-noise replay probe: same images/state/task/noise, eager versus graph,
first-capture versus replay, and prompt-shape alternation. Record action deltas,
capture count, memory and time. This separates numerical behavior from sampling
and clock effects. A bitwise match is not assumed for different kernels.

Next use one real development simulation plus11 distinct synthetic clients to
measure charged-time sensitivity without12 simultaneous renderers. Keep this
load diagnostic separate from ordinary task-success estimates. If stock latency
dominates, test one focused change, such as fewer flow steps, against stock with
matched noise and then repeated development tasks. Select at most one finalist;
do not launch a broad knob sweep against holdouts.

### 3. Repair graph recapture only if profiling justifies it

The current graph image stays unpromoted. Prefer a fixed padded/bucketed context
with correct masks and position handling, or a strictly bounded cache, only after
output-parity and memory measurements. Do not install an unbounded per-prompt
cache or assume one graph consumes2GB. Permit one implementation and one
development comparison before reconsidering. Preserve the frozen graph20 cohort
until the revised runtime qualifies; record any changed hypothesis before use.

### 4. Data adaptation after an observed failure mechanism

The ten public demos may verify conversion, schema, normalization and one-step
training plumbing only. For a real fine-tune, first inspect a bounded manifest
subset of the public MolmoBot Franka in/on data, establish license/eligible objects,
successful trajectories, state/action/camera semantics and scene/object splits.
Cap an initial acquisition at10GB and200eligible successful episodes. Proceed
only if the subset is technically suitable and addresses a measured gap; no
wildcard10TB download. Compare frozen base versus adapted checkpoint and retain
the base. GR00T fine-tuning is a fallback with a useful pipeline, not the next
default given its current development result.

LIBERO checkpoints require different controllers/normalization and have lower
near-term value than MolmoBot's DROID contract. Unchanged GR00T and horizon6 are
deprioritized. Quantization and model routing require their own evidence and are
not assumed to improve success or fit.

## Validation and promotion rules

- Existing pick20 and next-to10 are consumed; frozen graph20 and GR00T20 remain
  untouched. No outcome-driven reassignment. No tuning on official result tasks.
- Before any finalist outcomes, freeze a new80episode public validation manifest:
  44pick,32in/on,4next-to (the descriptive55/40/5 mix of our official run), with
  balanced shoulder order and exclusions for development, demos and previously
  tested scenes where metadata permits. Record dataset revisions, hashes and
  possible pretrained-data overlap. This is local validation, not a replica of
  hidden evaluation. Reserve a second independently drawn block for confirmation.
- Run finalist versus stock MolmoAct2 and pi0.5 with fixed cohort/environment
  seeds; store independent policy-noise seeds and interleave/reverse run order.
  Report counts, paired discordances, intervals, per-family and per-view outcomes,
  unscored/failures, timing and resources. Do not hide unscored cases or select
  successful retries. Report repeated stochastic trials separately from episodes.
- Advance when the predeclared primary comparison has positive lower95% paired
  confidence bound, acceptable per-family performance and no reliability failure.
  If inconclusive, use only the predeclared confirmation block or retain the
  incumbent; do not repeatedly peek and enlarge until significant. A local50%
  estimate is not the official target and does not authorize submission.
- Before requesting an official submission, assemble a tested registry manifest
  digest, denied-network startup, image-size/license proof, protocol/version
  compatibility evidence, runtime limits and concrete comparison. Recheck live
  rules/quota and obtain explicit human approval for that digest.

## Execution controls

Only the reviewed handoff stop with SHA
`e17c182d191b1c41a963f7d4ecfb8c14458cc8504a5a42ed73661117c8bc80fc`
may be archived, after matching local and server copies to the authorization.
Any later/different stop remains binding. Refresh and immediately mirror live
quota before resuming, validate disk/guard, then start the dedicated watchdog and
rootless engine. All long jobs use `control/start-job.sh`, one at a time, under
the isolated task root. Use the active native model directly; workers are optional.
Check quota every minute/four calls and stop at<=25% or unknown. Never spend reset
credits or paid APIs. Install a five-minute continuation heartbeat on this new
chat, quiet while nothing actionable changes. Save every outcome before moving on.

## Primary sources checked

- [Current competition rules](https://competition.phail.ai/rules), especially
  thinking time,12sessions,15second calls and permissible data.
- [Current official image/hardware guide](https://github.com/Positronic-Robotics/positronic/blob/main/docs/nebius-competition.md).
- [Pinned MolmoAct2 graph implementation](https://huggingface.co/allenai/MolmoAct2-DROID/blob/d8c1abd8a27d8e859455bbe514df2bcc617db0fb/inference.py)
  and [action sampler](https://huggingface.co/allenai/MolmoAct2-DROID/blob/d8c1abd8a27d8e859455bbe514df2bcc617db0fb/modeling_molmoact2.py).
- [Pinned MolmoBot training/deployment recipe](https://github.com/allenai/MolmoBot/blob/33c0ca77bf6062a23d60ffd4a6859334c4a46d30/MolmoBot/README.md),
  loader and inference wrapper at that same revision.
- Local Positronic `00fdd933f22158a9cbe6d97c5b19c2935df35c1b`:
  `policy/executor.py`, `cfg/eval/sim/molmo.py`, `vendors/molmoact2/policy.py`,
  workspace package metadata and native processor declarations.
