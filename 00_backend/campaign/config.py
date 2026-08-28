from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RunnerMode(str, Enum):
    DETERMINISTIC = "deterministic"
    ADK = "adk"


class Settings(BaseSettings):
    """Typed backend configuration sourced from environment variables or `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    campaign_runner_mode: RunnerMode = RunnerMode.DETERMINISTIC
    port: int = Field(default=8080, ge=1, le=65535)
    log_level: str = "info"

    gemini_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    google_genai_use_vertexai: bool = False
    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"

    @computed_field
    @property
    def runner_mode(self) -> RunnerMode:
        """Convenient internal name while preserving CAMPAIGN_RUNNER_MODE externally."""
        return self.campaign_runner_mode

    @property
    def adk_auth_mode(self) -> str:
        if self.google_genai_use_vertexai:
            return "vertex_ai"
        if self.gemini_api_key or self.google_api_key:
            return "api_key"
        return "ambient"


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention configuration snapshot per process."""
    return Settings()
