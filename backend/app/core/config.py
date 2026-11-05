from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore"
    )
    database_url: str
    jwt_secret_key: SecretStr = Field(min_length=32)
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-haiku-5-5"


@lru_cache
def get_settings() -> Settings:
    return Settings()
