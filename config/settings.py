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


settings = Settings()
