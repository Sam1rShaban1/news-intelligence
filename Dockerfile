FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
ENV PYTHONPATH=/app

# System deps for newspaper4k, lxml, psycopg2, healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libxml2-dev libxslt1-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir . 2>/dev/null; \
    pip install --no-cache-dir \
    "sqlalchemy[asyncio]>=2.0" \
    "psycopg2-binary>=2.9" \
    "alembic>=1.13" \
    "httpx>=0.27" \
    "feedparser>=6.0" \
    "newspaper4k[lxml]>=0.9" \
    "apscheduler>=3.10" \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.30" \
    "pydantic-settings>=2.0" \
    "streamlit>=1.35" \
    "vaderSentiment>=3.3" \
    "pgvector>=0.3" \
    "gliner2-onnx>=0.1" \
    "onnxruntime>=1.18" \
    "pyyaml>=6.0" \
    "lxml"

COPY . .

ENTRYPOINT ["python"]
