"""Global configuration loaded from environment variables with sane defaults."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "NEWS_", "env_file": ".env"}

    # Database
    database_url: str = "postgresql://news:news@localhost:5432/news_intelligence"

    # Workers
    poll_interval_seconds: int = 60
    batch_size: int = 10
    zombie_timeout_minutes: int = 5
    max_retries: int = 3

    # NER service tuning (the separate `ner` worker)
    ner_batch_size: int = 50
    ner_poll_interval: float = 2.0
    ner_zombie_min: int = 5
    ner_max_retries: int = 3

    # HTTP
    http_timeout: int = 15
    user_agent: str = (
        "Mozilla/5.0 (compatible; NewsIntelligence/0.1; +https://github.com/news-intelligence)"
    )

    # Scheduler
    scan_interval_minutes: int = 60

    # Logging
    log_level: str = "INFO"

    # Paths
    config_dir: Path = Path("config")

    # GLiNER2 ONNX model (multilingual NER, runs in the separate `ner` service)
    gliner_model: str = "lmo3/gliner2-multi-v1-onnx"
    # Pinned model-repo revision (commit) for reproducible downloads. Update this
    # when you intentionally upgrade the NER model.
    gliner_model_revision: str = "e52892db1d20f0c2ac18e3c7f00b1569fa2fa895"
    # Optional supply-chain check: sha256 of any one of the model's `.onnx` files.
    # Leave empty to skip verification. The loader refuses to use the model if no
    # `.onnx` file matches this value.
    gliner_model_sha256: str = ""

    # Sentiment: auto = transformer if model present else lexicon/VADER;
    # transformer = force ONNX (falls back if missing); lexicon = skip ONNX.
    sentiment_model: str = "auto"
    sentiment_model_path: str = "/app/models/sentiment.onnx"

    # API protection. If `api_key` is set, every API route (except /health) requires
    # an `X-API-Key` header matching it. Leave empty to disable auth (single-tenant,
    # behind a trusted reverse proxy).
    api_key: str = ""

    # Comma-separated list of allowed CORS origins for the browser UI. Use "*" to
    # allow any origin, or a comma-separated list e.g. "http://localhost:8501".
    cors_origins: str = "http://localhost:3000,http://localhost:8501,http://127.0.0.1:8501"

    # Feature flags. A single image can run on a Raspberry Pi (heavy ML off) or a
    # VPS (full features). The heavy libraries (onnxruntime, gliner2-onnx,
    # tokenizers, pgvector) are only installed in the `vps` Docker target; when
    # they are absent the features below self-disable, so these flags are a runtime
    # safety switch on top of that. Set to "false" in docker-compose.pi.yml.
    feature_ner: bool = True
    feature_embeddings: bool = True
    feature_pdf_export: bool = True
    feature_alerts: bool = True


settings = Settings()
