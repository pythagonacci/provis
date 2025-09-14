from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Tuple, Optional

def _bool(env: str, default: bool = False) -> bool:
    v = os.getenv(env)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")

@dataclass
class Settings:
    # Core data settings
    DATA_DIR: str = os.getenv("DATA_DIR", "data")
    MAX_FILE_MB: int = int(os.getenv("MAX_FILE_MB", "2"))
    MAX_ZIP_MB: int = int(os.getenv("MAX_ZIP_MB", "40"))
    MAX_FILES: int = int(os.getenv("MAX_FILES", "1000"))
    IGNORED_DIRS: Tuple[str, ...] = tuple(os.getenv("IGNORED_DIRS", ".git,node_modules,.next,dist,build,.venv,__pycache__").split(","))
    IGNORED_EXTS: Tuple[str, ...] = tuple(os.getenv("IGNORED_EXTS", ".png,.jpg,.jpeg,.gif,.bmp,.ico,.lock,.pdf,.mp4,.mp3,.mov").split(","))

    # LLM settings with robust defaults
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.0"))  # Deterministic
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2000"))
    LLM_JSON_MODE: bool = _bool("LLM_JSON_MODE", True)
    LLM_CACHE: bool = _bool("LLM_CACHE", True)
    LLM_CONCURRENCY: int = int(os.getenv("LLM_CONCURRENCY", "4"))
    LLM_PER_CALL_TIMEOUT: int = int(os.getenv("LLM_PER_CALL_TIMEOUT", "30"))
    LLM_PER_REPO_TOKEN_BUDGET: int = int(os.getenv("LLM_PER_REPO_TOKEN_BUDGET", "50000"))
    
    # Parsing settings
    PARSE_PER_FILE_TIMEOUT: int = int(os.getenv("PARSE_PER_FILE_TIMEOUT", "10"))
    BIG_FILE_SIZE_THRESHOLD: int = int(os.getenv("BIG_FILE_SIZE_THRESHOLD", "1000000"))  # 1MB
    BIG_FILE_LINES_THRESHOLD: int = int(os.getenv("BIG_FILE_LINES_THRESHOLD", "5000"))
    PARSE_BATCH_SIZE: int = int(os.getenv("PARSE_BATCH_SIZE", "250"))
    PARSE_SHARD_SIZE: int = int(os.getenv("PARSE_SHARD_SIZE", "100"))
    
    # Concurrency and limits
    NODE_PARSE_CONCURRENCY: int = int(os.getenv("NODE_PARSE_CONCURRENCY", "4"))
    LLM_CONCURRENCY: int = int(os.getenv("LLM_CONCURRENCY", "4"))
    
    # Degradation toggles
    ENABLE_ALIAS_BRUTE_FORCE: bool = _bool("ENABLE_ALIAS_BRUTE_FORCE", True)
    ENABLE_DYNAMIC_IMPORT_WILDCARDS: bool = _bool("ENABLE_DYNAMIC_IMPORT_WILDCARDS", True)
    ENABLE_TOLERANT_STRING_LITERAL_SCAN: bool = _bool("ENABLE_TOLERANT_STRING_LITERAL_SCAN", True)
    
    # Legacy LLM budget settings (for backward compatibility)
    LLM_FILE_SUMMARY_BUDGET: int = int(os.getenv("LLM_FILE_SUMMARY_BUDGET", "100"))
    LLM_CAP_BUDGET: int = int(os.getenv("LLM_CAP_BUDGET", "20"))

    # CORS
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000")

settings = Settings()