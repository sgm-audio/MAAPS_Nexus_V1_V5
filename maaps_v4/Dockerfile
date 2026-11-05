# MAAPS v4.0 - Multi-Stage Dockerfile for HeartMuLa GPU Swarm
# Production-ready, self-hosted, scalable audio generation

# =====================================
# Stage 1: Weight Retriever (CPU)
# Download HeartMuLa weights via HF CLI
# =====================================
FROM python:3.12-slim as weight-retriever

ENV DEBIAN_FRONTEND=noninteractive
ENV HF_HOME=/models

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    git-lfs \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && git lfs install

RUN pip install --no-cache-dir huggingface_hub

# Download HeartMuLa model to cache
ARG HEARTMULA_MODEL=HeartMuLa-oss-3B
# For testing, use MusicGen as fallback
RUN huggingface-cli download facebook/musicgen-small --local-dir /models/musicgen-small || true

# If you have access to HeartMuLa, uncomment:
# RUN huggingface-cli download heartmu/HeartMuLa-oss-3B --local-dir /models/HeartMuLa-oss-3B || true

# =====================================
# Stage 2: GPU Runtime
# Full MAAPS v4.0 with baked models
# =====================================
FROM nvidia/cuda:12.1-cudnn8-runtime-ubuntu22.04 as gpu-runtime

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV HF_HOME=/models
ENV CUDA_VISIBLE_DEVICES=0

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3-pip \
    ffmpeg \
    libsndfile1 \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/bin/python3.12 /usr/bin/python

WORKDIR /app

# Copy requirements first for layer caching
COPY maaps_v4/requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121 && \
    pip install -r requirements.txt

# Copy models from retriever stage
COPY --from=weight-retriever /models /models

# Copy application code
COPY maaps_v4/ ./maaps_v4/
COPY main.py .

# Create output directory
RUN mkdir -p /tmp/maaps_output && chmod 777 /tmp/maaps_output

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import torch; print('GPU:', torch.cuda.is_available())" || exit 1

# Expose ports
EXPOSE 8000 8765

# Default command
CMD ["python", "main.py"]

# =====================================
# Stage 3: Development Override
# Mount local code for development
# =====================================
FROM gpu-runtime as dev

# Override with local volume mount
VOLUME ["/app/maaps_v4"]

# Enable hot reload
ENV WATCHFILES_FORCE_POLLING=true

CMD ["python", "-m", "uvicorn", "maaps_v4.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
