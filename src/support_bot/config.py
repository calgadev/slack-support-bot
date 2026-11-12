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

    # Storage
    data_dir: Path = Path("data")

    # Logging
    log_level: str = "INFO"

    # Health
    heartbeat_interval_seconds: int = Field(default=30, ge=1)
    heartbeat_max_age_seconds: int = Field(default=90, ge=1)

    @property
    def heartbeat_path(self) -> Path:
        return self.data_dir / "heartbeat"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
