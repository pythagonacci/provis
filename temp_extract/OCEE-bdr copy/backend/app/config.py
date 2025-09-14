from __future__ import annotations

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    """
    Centralized application configuration.

    Loads from environment with sensible local defaults so the app
    can run end-to-end in stub mode without extra setup.
    """

    # Core
    DB_URL: str = "sqlite:///./bdr.db"
    APP_BASE_URL: str = "http://localhost:8000"
    FILE_STORAGE_DIR: str = "./app/generated"

    # AI
    OPENAI_API_KEY: Optional[str] = None
    STUB_MODE: bool = True  # True => deterministic local stubs (no API calls)

    # CORS
    ALLOWED_ORIGINS: str = "*"  # CSV list or "*" for all (tighten later)

    # Content limits (kept here so services/pdf/template can read the same values)
    TITLE_MAX_CHARS: int = 200
    BULLET_MAX_CHARS: int = 500
    MAX_BULLETS: int = 8

    class Config:
        env_file = ".env"
        extra = "ignore"

    @field_validator("FILE_STORAGE_DIR")
    @classmethod
    def _normalize_storage_dir(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("APP_BASE_URL")
    @classmethod
    def _normalize_base_url(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def _normalize_origins(cls, v: str) -> str:
        # Normalize whitespace; routers/middleware can split on comma
        return ",".join([s.strip() for s in v.split(",")]) if v and v != "*" else v


# Singleton settings instance to import elsewhere
settings = Settings()
