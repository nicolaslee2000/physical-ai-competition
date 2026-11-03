# Prepared recipe only: wheel resolution, stage manifest and actual build remain unverified.
FROM pytorch/pytorch@sha256:417bd75df6365104c283ea4c1651fb3530d9eb5a4c2fafa51943cff2a94e6385
ENV TASK_ROOT=/opt/hderc-internal/nick/physical-ai-competition \
    PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1 \
    TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
# Dependency wheelhouse is built/reviewed separately. No network package resolution in this image.
COPY requirements.lock /staging/requirements.lock
COPY wheelhouse/ /staging/wheelhouse/
RUN python -c "import sys,torch; assert sys.version_info[:2]==(3,11); assert torch.__version__.startswith('2.8.'); assert torch.version.cuda=='12.8'" \
 && python -m venv --system-site-packages "$TASK_ROOT/serving/.venv" \
 && "$TASK_ROOT/serving/.venv/bin/python" -m pip install --no-index --find-links=/staging/wheelhouse --require-hashes --no-deps -r /staging/requirements.lock \
 && "$TASK_ROOT/serving/.venv/bin/python" -m pip check \
 && "$TASK_ROOT/serving/.venv/bin/python" -c "import torch; assert torch.__version__.startswith('2.8.'); assert torch.version.cuda=='12.8'"
COPY molmobot_candidate/ /opt/hderc-internal/nick/physical-ai-competition/src/molmobot_candidate/
COPY artifacts/ /opt/hderc-internal/nick/physical-ai-competition/artifacts/molmobot/
COPY notices/ /opt/hderc-internal/nick/physical-ai-competition/notices/
ENV PYTHONPATH=/opt/hderc-internal/nick/physical-ai-competition/src \
    TMPDIR=/opt/hderc-internal/nick/physical-ai-competition/tmp \
    HF_HOME=/opt/hderc-internal/nick/physical-ai-competition/cache/huggingface \
    XDG_CACHE_HOME=/opt/hderc-internal/nick/physical-ai-competition/cache \
    TORCH_HOME=/opt/hderc-internal/nick/physical-ai-competition/cache/torch \
    TORCH_EXTENSIONS_DIR=/opt/hderc-internal/nick/physical-ai-competition/cache/torch-extensions \
    TRITON_CACHE_DIR=/opt/hderc-internal/nick/physical-ai-competition/cache/triton \
    CUDA_CACHE_PATH=/opt/hderc-internal/nick/physical-ai-competition/cache/cuda
RUN mkdir -p "$TMPDIR" \
 && "$TASK_ROOT/serving/.venv/bin/python" -m molmobot_candidate.serve --verify-only
EXPOSE 8000
ENTRYPOINT ["/opt/hderc-internal/nick/physical-ai-competition/serving/.venv/bin/python", "-m", "molmobot_candidate.serve"]
