# Team Nick — Physical AI Competition

Initial policy: the official Positronic π0.5 DROID baseline, pinned by image digest in `Dockerfile`.

Build and publish:

```sh
docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
  -t ghcr.io/nicolaslee2000/physical-ai-competition:baseline-v1 --push .
```

The test script is derived from Positronic commit `00fdd933f22158a9cbe6d97c5b19c2935df35c1b`, under Apache-2.0. It checks readiness from outside a container on a dedicated internal network with no egress. Local changes select the GPU through `POLICY_TEST_GPU` (default 0), cap CPU/RAM, and disable JAX GPU preallocation for testing on a shared machine. These test settings are not baked into the submitted image.

```sh
POLICY_TEST_GPU=GPU-UUID bash docker/test_policy_image.sh --gpu \
  ghcr.io/nicolaslee2000/physical-ai-competition@sha256:DIGEST
```

The readiness test verifies offline startup and the authenticated keepalive endpoint. It does not establish task success or full inference performance.

Official guide: https://github.com/Positronic-Robotics/positronic/blob/main/docs/nebius-competition.md
