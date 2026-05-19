# PHANTOM backend — Python 3.11, CPU-only torch
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TRANSFORMERS_CACHE=/app/models \
    SENTENCE_TRANSFORMERS_HOME=/app/models \
    HF_HUB_OFFLINE=1

WORKDIR /app

# System deps: build essentials for any source-only wheels, libs for pikepdf/pymupdf
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libffi-dev \
        libssl-dev \
        libjpeg-dev \
        zlib1g-dev \
        libxml2-dev \
        libxslt1-dev \
        libqpdf-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first (avoids pulling CUDA wheels)
RUN pip install --no-cache-dir torch==2.2.1 \
        --index-url https://download.pytorch.org/whl/cpu

# Install remaining Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Models are mounted in via volume; do not bake them into the image
VOLUME ["/app/models"]

EXPOSE 8000

# Healthcheck — backend exposes /health
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
