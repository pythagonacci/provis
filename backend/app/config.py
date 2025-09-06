from pathlib import Path
from pydantic import BaseModel
import os

class Settings(BaseModel):
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "data"))
    MAX_ZIP_MB: int = int(os.getenv("MAX_ZIP_MB", "40"))
    MAX_FILES: int = int(os.getenv("MAX_FILES", "5000"))
    MAX_FILE_MB: int = int(os.getenv("MAX_FILE_MB", "5"))
    JOB_RETENTION_HOURS: int = int(os.getenv("JOB_RETENTION_HOURS", "24"))
    IGNORED_DIRS: tuple[str, ...] = (
        ".git", "node_modules", ".next", "dist", "build", "coverage", ".cache"
    )
    IGNORED_EXTS: tuple[str, ...] = (
        ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".mov", ".zip", ".tar", ".gz", ".pdf", ".exe", ".dll"
    )

settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
