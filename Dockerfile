FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# System deps for newspaper4k, lxml, psycopg2, healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libxml2-dev libxslt1-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install core Python deps first (layer caching). NOTE: this intentionally omits
# the heavy ML stack (onnxruntime / gliner2-onnx / tokenizers / pgvector) so the
# image stays small and buildable on a Raspberry Pi. The heavy deps are added
# only in the `vps` target below.
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    "sqlalchemy[asyncio]>=2.0" \
    "psycopg2-binary>=2.9" \
    "alembic>=1.13" \
    "httpx>=0.27" \
    "feedparser>=6.0" \
    "newspaper4k[lxml]>=0.9" \
    "apscheduler==3.10.4" \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.30" \
    "pydantic-settings>=2.0" \
    "vaderSentiment>=3.3" \
    "langid>=1.1.6" \
    "beautifulsoup4>=4.12" \
    "pyyaml>=6.0" \
    "nltk>=3.8" \
    "lxml"

# Pre-download the NLTK corpora newspaper4k uses for richer author/keyword
# extraction. Best-effort: a transient download failure must not break the
# build — newspaper4k degrades gracefully without them.
RUN python -m nltk.downloader -d /usr/share/nltk_data punkt punkt_tab averaged_perceptron_tagger || true
ENV NLTK_DATA=/usr/share/nltk_data

COPY . .

# ---- pi: lightweight tier (no heavy ML) ----
# Heavy features self-disable via the FEATURE_* flags in config/settings.py when
# their libraries are absent, so this image runs the full fetch/extract/sentiment
# pipeline on a Pi 4B without ONNX or pgvector.
FROM base AS pi

# ---- vps: full tier (default build target) ----
# Embeddings + multilingual NER + baked ONNX sentiment model + PDF export.
# Use `docker compose build --target pi` for a Raspberry Pi.
FROM base AS vps
RUN pip install --no-cache-dir \
    "gliner2-onnx>=0.1" \
    "onnxruntime>=1.18" \
    "tokenizers>=0.19" \
    "pgvector>=0.3" \
    "reportlab>=4.0"

# Bake the multilingual ONNX sentiment model (int8 quantized, ~279 MB).
# Source: onnx-community/twitter-xlm-roberta-base-sentiment-ONNX
RUN mkdir -p /app/models && \
    curl -sL "https://huggingface.co/onnx-community/twitter-xlm-roberta-base-sentiment-ONNX/resolve/main/onnx/model_int8.onnx" \
         -o /app/models/sentiment.onnx && \
    curl -sL "https://huggingface.co/onnx-community/twitter-xlm-roberta-base-sentiment-ONNX/resolve/main/tokenizer.json" \
         -o /app/models/sentiment_tokenizer.json

ENTRYPOINT ["python"]
