from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Tuple

def _bool(env: str, default: bool = False) -> bool:
    v = os.getenv(env)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")

@dataclass
class Settings:
    DATA_DIR: str = os.getenv("DATA_DIR", "data")
    MAX_FILE_MB: int = int(os.getenv("MAX_FILE_MB", "2"))
    MAX_ZIP_MB: int = int(os.getenv("MAX_ZIP_MB", "40"))
    MAX_FILES: int = int(os.getenv("MAX_FILES", "1000"))
    IGNORED_DIRS: Tuple[str, ...] = tuple(os.getenv("IGNORED_DIRS", ".git,node_modules,.next,dist,build,.venv,__pycache__").split(","))
    IGNORED_EXTS: Tuple[str, ...] = tuple(os.getenv("IGNORED_EXTS", ".png,.jpg,.jpeg,.gif,.bmp,.ico,.lock,.pdf,.mp4,.mp3,.mov").split(","))

    # LLM settings (real model by default)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "800"))
    LLM_CACHE: bool = _bool("LLM_CACHE", True)
    LLM_CONCURRENCY: int = int(os.getenv("LLM_CONCURRENCY", "4"))
    
    # Step 3 LLM budget settings
    LLM_FILE_SUMMARY_BUDGET: int = int(os.getenv("LLM_FILE_SUMMARY_BUDGET", "100"))
    LLM_CAP_BUDGET: int = int(os.getenv("LLM_CAP_BUDGET", "20"))

    # CORS
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000")

settings = Settings()