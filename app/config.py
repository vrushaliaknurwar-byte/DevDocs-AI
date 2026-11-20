from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Read strictly from environment variables
        extra="ignore"
    )

    # Gemini API Key
    GEMINI_API_KEY: str = Field(default="", description="Gemini API Key")

    # PostgreSQL Database URL (Render / cloud providers often use postgres:// or postgresql://)
    DATABASE_URL: str = Field(
        default="postgresql://devdocs:devdocs_password@localhost:5432/devdocs",
        description="Database connection URL"
    )

    # Embedding and Generation Models
    EMBEDDING_MODEL: str = Field(default="gemini-embedding-001", description="Gemini embedding model name")
    GENERATION_MODEL: str = Field(default="gemini-3.5-flash", description="Gemini chat generation model name")
    EMBEDDING_DIMENSIONS: int = Field(default=768, description="pgvector vector dimensions")

    # App Environment
    APP_ENV: str = Field(default="production", description="Application environment")
    HOST: str = Field(default="0.0.0.0", description="API bind host")
    PORT: int = Field(default=8000, description="API port")

    # Operational settings
    CLONE_TIMEOUT_SECONDS: int = Field(default=120, description="Timeout for git shallow clone in seconds")
    MAX_FILE_SIZE_BYTES: int = Field(default=1_000_000, description="Max individual file size in bytes to parse (1MB)")
    MAX_REPO_SIZE_MB: int = Field(default=50, description="Max repository size in MB allowed for ingestion")

    # Rate limiting (requests per hour per IP)
    RATE_LIMIT_REPOS_PER_HOUR: int = Field(default=5, description="Max POST /repos requests per hour per IP")
    RATE_LIMIT_ASK_PER_HOUR: int = Field(default=30, description="Max POST /repos/{id}/ask requests per hour per IP")

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if isinstance(v, str):
            clean_url = v.strip()
            # If DATABASE_URL starts with "postgres://", convert it to "postgresql://"
            if clean_url.startswith("postgres://"):
                clean_url = "postgresql://" + clean_url[len("postgres://"):]
            return clean_url
        return v


@lru_cache()
def get_settings() -> Settings:
    return Settings()
