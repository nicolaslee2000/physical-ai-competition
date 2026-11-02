# Team Nick — Physical AI Competition

Initial policy: the official Positronic π0.5 DROID baseline, pinned by image digest in `Dockerfile`.

Build and publish:

```sh
docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
  -t ghcr.io/nicolaslee2000/physical-ai-competition:baseline-v1 --push .
```

The test script is derived from Positronic commit `00fdd933f22158a9cbe6d97c5b19c2935df35c1b`, under Apache-2.0. It checks readiness from outside a container on a dedicated internal network with no egress. Local changes select the GPU through CDI and `POLICY_TEST_GPU` (default 0), cap RAM at 28 GiB with no swap, disable JAX GPU preallocation, and support probing from the rootless engine network namespace. These test settings are not baked into the submitted image.

```sh
POLICY_TEST_GPU=GPU-UUID bash docker/test_policy_image.sh --gpu \
  ghcr.io/nicolaslee2000/physical-ai-competition@sha256:DIGEST
```

The readiness test verifies offline startup and the authenticated keepalive endpoint. It does not establish task success or full inference performance.

Official guide: https://github.com/Positronic-Robotics/positronic/blob/main/docs/nebius-competition.md

## Server storage isolation

All task files and Docker data live in `/opt/hderc-internal/nick/physical-ai-competition/`.
`docker/start-local-engine.sh` starts a dedicated rootless Docker engine as a transient user service, pins its processes to four CPU cores and sets a 28 GiB service memory limit. Individual model containers also have a 28 GiB memory limit. It does not use the shared Docker engine or its image store.

Use `bash docker/engine.sh ...` instead of plain `docker` for all server commands. The wrapper selects the task's socket, credentials directory, cache and temporary directory. Use `bash docker/test-local.sh IMAGE` for the offline readiness check on the server's RTX PRO 6000.

Stop only this engine with `XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user stop nick-physical-ai-docker`. The source and downloaded images remain under the task directory for reuse. No competition API key is copied to the server.
