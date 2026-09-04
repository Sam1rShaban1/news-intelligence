FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Every service command is `python -m ...` / `python scripts/...`, so the
# entrypoint must apply to ALL build targets (vps and pi alike).
ENTRYPOINT ["python"]

# System deps for newspaper4k, lxml, psycopg2, healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libxml2-dev libxslt1-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install core Python deps from a compiled, fully-pinned lockfile (reproducible
# builds; see requirements/). NOTE: this intentionally omits the heavy ML stack
# (onnxruntime / gliner2-onnx / tokenizers / pgvector) so the image stays small
# and buildable on a Raspberry Pi. The heavy deps are added only in `vps`.
COPY pyproject.toml requirements/base.lock /tmp/
RUN pip install --no-cache-dir -r /tmp/base.lock

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
# Run as a non-root user in the final image.
RUN useradd -m -u 10001 -s /usr/sbin/nologin app && chmod -R a+rX /usr/share/nltk_data
USER app

# ---- vps: full tier (default build target) ----
# Embeddings + multilingual NER + baked ONNX sentiment model + PDF export.
# Use `docker compose build --target pi` for a Raspberry Pi.
FROM base AS vps
COPY requirements/vps.lock /tmp/vps.lock
RUN pip install --no-cache-dir -r /tmp/vps.lock

# Bake the multilingual ONNX sentiment model (int8 quantized, ~279 MB).
# Source: onnx-community/twitter-xlm-roberta-base-sentiment-ONNX
# Pinned by sha256 and verified at build time (supply-chain hardening).
ARG MODEL_ONNX_SHA256=6c7c4e804129149d58eb1d11a576129f4270f46134dd074315b8aea05d178e20
ARG TOKENIZER_SHA256=b74659c780d49afad7a7b9799868f75cbd3014fb6c34956e85a793028d38094a
RUN mkdir -p /app/models && \
    curl -fsSL "https://huggingface.co/onnx-community/twitter-xlm-roberta-base-sentiment-ONNX/resolve/main/onnx/model_int8.onnx" \
         -o /app/models/sentiment.onnx && \
    curl -fsSL "https://huggingface.co/onnx-community/twitter-xlm-roberta-base-sentiment-ONNX/resolve/main/tokenizer.json" \
         -o /app/models/sentiment_tokenizer.json && \
    echo "${MODEL_ONNX_SHA256}  /app/models/sentiment.onnx" | sha256sum -c - && \
    echo "${TOKENIZER_SHA256}  /app/models/sentiment_tokenizer.json" | sha256sum -c - && \
    chmod -R a+rX /app/models

# Run as a non-root user in the final image.
RUN useradd -m -u 10001 -s /usr/sbin/nologin app && chmod -R a+rX /usr/share/nltk_data
USER app
