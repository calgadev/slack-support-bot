"""Application settings loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Every field maps to an upper-case env var of the same name."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Slack (only required when running the bot, not for ingest/evals)
    slack_bot_token: SecretStr | None = None
    slack_app_token: SecretStr | None = None

    # Gemini
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_embedding_model: str = "gemini-embedding-2"
    gemini_embedding_dim: int = Field(default=768, ge=128, le=3072)
    gemini_timeout_seconds: float = Field(default=30.0, gt=0)
    gemini_max_attempts: int = Field(default=4, ge=1)
    gemini_max_output_tokens: int = Field(default=1024, ge=64)

    # Input guardrails
    max_input_chars: int = Field(default=2000, ge=100)

    # Retrieval
    knowledge_base_dir: Path = Path("knowledge_base")
    retrieval_top_k: int = Field(default=4, ge=1, le=20)
    retrieval_min_score: float = Field(default=0.5, ge=-1.0, le=1.0)

    # Tickets
    pending_action_ttl_seconds: int = Field(default=900, ge=60)
    cleanup_interval_seconds: int = Field(default=600, ge=60)

    # Storage
    data_dir: Path = Path("data")

    # Logging
    log_level: str = "INFO"

    # Health
    heartbeat_interval_seconds: int = Field(default=30, ge=1)
    heartbeat_max_age_seconds: int = Field(default=90, ge=1)

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "support_bot.db"

    @property
    def heartbeat_path(self) -> Path:
        return self.data_dir / "heartbeat"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
