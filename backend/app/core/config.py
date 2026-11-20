from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "Financinio"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Database (Neon Postgres in prod, SQLite dev fallback if not provided)
    database_url: str = "sqlite+aiosqlite:///./financinio_dev.db"

    # Security / JWT
    jwt_secret_key: str = "dev-insecure-change-me-in-production-financinio-key-2026"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    # Pluggable File Storage
    storage_backend: Literal["local", "s3"] = "local"
    local_storage_dir: str = "./uploads"
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str = "auto"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    # Upstash Vector
    upstash_vector_rest_url: str | None = None
    upstash_vector_rest_token: str | None = None

    # Provider-agnostic LLM configuration
    llm_provider: Literal["google_genai", "openai", "anthropic"] = "google_genai"
    llm_model_fast: str = "gemini-2.5-flash"
    llm_model_vision: str = "gemini-2.5-flash"
    google_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # LangSmith
    langchain_tracing_v2: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")
    langchain_endpoint: str = Field(
        default="https://api.smith.langchain.com", alias="LANGCHAIN_ENDPOINT"
    )
    langchain_api_key: str | None = Field(default=None, alias="LANGCHAIN_API_KEY")
    langchain_project: str = Field(default="financinio-dev", alias="LANGCHAIN_PROJECT")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def upstash_configured(self) -> bool:
        return bool(self.upstash_vector_rest_url and self.upstash_vector_rest_token)

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "google_genai":
            return bool(self.google_api_key)
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        return False

    @property
    def langsmith_configured(self) -> bool:
        return bool(self.langchain_tracing_v2 and self.langchain_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
