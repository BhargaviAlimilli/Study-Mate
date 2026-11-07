from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore"
    )
    api_public_url: str = "http://127.0.0.1:8000"
    database_url: str
    jwt_secret_key: SecretStr = Field(min_length=32)
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-haiku-5-5"
    qdrant_url: str = "http://127.0.0.1:6335"
    qdrant_collection_name: str = "study_mate"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    ollama_model: str | None = None
    ollama_base_url: str = "http://127.0.0.1:11434"
    speech_transcription_model: str = "whisper-1"
    speech_generation_model: str = "tts-1"
    frontend_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    background_ingestion: bool = True
    redis_url: str = "redis://127.0.0.1:6380/0"
    ingestion_timeout_seconds: int = Field(default=900, ge=30, le=3600)


@lru_cache
def get_settings() -> Settings:
    return Settings()
