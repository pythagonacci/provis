from fastapi import UploadFile
from pathlib import Path
from .config import settings
from .utils.file_safety import safe_extract_zip

async def stage_upload(repo_dir: Path, upload: UploadFile) -> Path:
    """Save uploaded zip to disk; return path."""
    tmp_zip = repo_dir / "upload.zip"
    with open(tmp_zip, "wb") as f:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    return tmp_zip

def extract_snapshot(zip_path: Path, snapshot_dir: Path) -> int:
    return safe_extract_zip(
        zip_path, snapshot_dir,
        max_zip_bytes=settings.MAX_ZIP_MB * 1024 * 1024,
        max_files=settings.MAX_FILES,
        max_file_bytes=settings.MAX_FILE_MB * 1024 * 1024,
        ignored_dirs=settings.IGNORED_DIRS,
        ignored_exts=settings.IGNORED_EXTS,
    )
