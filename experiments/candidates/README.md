# DROID action-horizon candidates

These recipes start from the exact `positro/pi05-droid` image used for the published competition baseline, pinned by source-image digest. They change only `droid_pipe.horizon_sec` in `/positronic/positronic/vendors/openpi/server.py`; checkpoints, tokenizer, entrypoint, dependencies, and offline environment are inherited. The `RUN` checks that the pinned source contains exactly one expected baseline line and fails if it does not. No guessed CLI flag is used.

The source line is `droid_pipe = pipeline.override(codec=codecs.droid, ee_frame=None, horizon_sec=8 / 15)`. The neighboring `pipeline` config passes `fps` and `horizon_sec` to `ChunkedSchedule`; therefore the candidates test 6, 8 (baseline), or 10 frames at 15 fps. This is a hypothesis sweep, not a presumed improvement.

Build with the competition directory as context, substituting unique local or registry tags:

```sh
docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
  -f experiments/candidates/Dockerfile.horizon-6of15 \
  -t ghcr.io/nicolaslee2000/physical-ai-competition:horizon-6of15 .
docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
  -f experiments/candidates/Dockerfile.horizon-10of15 \
  -t ghcr.io/nicolaslee2000/physical-ai-competition:horizon-10of15 .
```

Resolve each built image's digest after push; do not reuse a moving tag for evaluation. Before any task scoring, compare each image's config/entrypoint and offline readiness with baseline using the competition's existing offline test. Then use only five paired development episodes as a screen, with identical seeds/tasks and shoulder-view coverage; record successes / attempts, per-episode steps and replans, latency p50/p95/max, failures, wall time, GPU memory, and first-inference time. Replan expectation is approximately episode frames divided by horizon frames; capture the actual count. If a candidate merits follow-up, test once on the untouched 20-episode holdout and preserve baseline. A readiness pass alone does not establish task quality. No GPU test or official submission is part of these recipes.
