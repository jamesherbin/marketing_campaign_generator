from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field, SecretStr, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RunnerMode(str, Enum):
    DETERMINISTIC = "deterministic"
    ADK = "adk"


class DatabaseMode(str, Enum):
    LOCAL = "local"
    CLOUD_SQL = "cloud_sql"


class DatabaseSettings(BaseSettings):
    """Validated when opening the database, never during module import."""

    model_config = SettingsConfigDict(
        env_prefix="DATABASE_", env_file=".env", extra="ignore",
        hide_input_in_errors=True,
    )

    mode: DatabaseMode = DatabaseMode.LOCAL
    url: SecretStr | None = None
    instance: str | None = None
    name: str | None = None
    user: str | None = None
    pool_min_size: int = Field(default=1, ge=1, le=100)
    pool_max_size: int = Field(default=10, ge=1, le=100)
    connect_timeout: float = Field(default=10, gt=0, le=120)
    command_timeout: float = Field(default=30, gt=0, le=300)
    shutdown_timeout: float = Field(default=10, gt=0, le=120)

    @model_validator(mode="after")
    def validate_connection(self) -> "DatabaseSettings":
        if self.pool_min_size > self.pool_max_size:
            raise ValueError("DATABASE_POOL_MIN_SIZE must not exceed DATABASE_POOL_MAX_SIZE")
        if self.mode == DatabaseMode.LOCAL:
            if not self.url or not self.url.get_secret_value().startswith(("postgres://", "postgresql://")):
                raise ValueError("DATABASE_URL must be a PostgreSQL URL in local mode")
            if any((self.instance, self.name, self.user)):
                raise ValueError("Cloud SQL fields must be unset in local mode")
        else:
            if self.url is not None:
                raise ValueError("DATABASE_URL must be unset in cloud_sql mode")
            if not all(value and value.strip() for value in (self.instance, self.name, self.user)):
                raise ValueError("Cloud SQL requires DATABASE_INSTANCE, DATABASE_NAME, and DATABASE_USER")
            if len(self.instance.split(":")) != 3 or not all(self.instance.split(":")):
                raise ValueError("DATABASE_INSTANCE must have project:region:instance format")
        return self


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
