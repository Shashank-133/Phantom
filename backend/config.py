"""PHANTOM backend configuration.

All settings come from environment variables (or .env file at project root).
Read by everything — services, workers, API routes.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = parent of backend/. Used to resolve relative paths (models/, keys/)
# the same way regardless of whether code is run from project root, backend/, or
# anywhere else (Celery worker, pytest, etc.).
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Postgres ---
    postgres_user: str = "phantom"
    postgres_password: str = "phantom_dev_pw"
    postgres_db: str = "phantom"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "phantom_dev_pw"

    # --- Redis / Celery ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # --- Backend ---
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    log_level: str = "INFO"
    env: str = "development"

    # --- CORS ---
    frontend_url: str = "http://localhost:5173"

    # --- ML model caches (paths relative to project root, or absolute) ---
    transformers_cache: str = "./models"
    sentence_transformers_home: str = "./models"

    # --- Optional Gemini for narrative ---
    gemini_api_key: str = ""

    # --- Crypto ---
    phantom_key_dir: str = "./keys"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_dsn_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def _resolve(self, raw: str) -> Path:
        """Resolve a path: absolute paths kept as-is, relative paths anchored at PROJECT_ROOT."""
        p = Path(raw)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()

    @property
    def key_dir_path(self) -> Path:
        p = self._resolve(self.phantom_key_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def models_path(self) -> Path:
        return self._resolve(self.transformers_cache)

    @property
    def sentence_transformers_path(self) -> Path:
        return self._resolve(self.sentence_transformers_home)


@lru_cache
def get_settings() -> Settings:
    return Settings()
