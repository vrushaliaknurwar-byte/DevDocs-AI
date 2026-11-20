from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.txt"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Gemini API
    GEMINI_API_KEY: str = Field(default="", description="Gemini API Key")

    # PostgreSQL Database URL
    DATABASE_URL: str = Field(
        default="postgresql://devdocs:devdocs_password@localhost:5432/devdocs",
        description="Database connection URL"
    )

    # Embedding and Generation Models
    EMBEDDING_MODEL: str = Field(default="gemini-embedding-001", description="Gemini embedding model name")
    GENERATION_MODEL: str = Field(default="gemini-3.5-flash", description="Gemini chat generation model name")
    EMBEDDING_DIMENSIONS: int = Field(default=768, description="pgvector vector dimensions")

    # App Environment
    APP_ENV: str = Field(default="development", description="Application environment")
    HOST: str = Field(default="0.0.0.0", description="API bind host")
    PORT: int = Field(default=8000, description="API port")

    # Operational settings
    CLONE_TIMEOUT_SECONDS: int = Field(default=120, description="Timeout for git shallow clone in seconds")
    MAX_FILE_SIZE_BYTES: int = Field(default=1_000_000, description="Max file size in bytes to parse (1MB)")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
