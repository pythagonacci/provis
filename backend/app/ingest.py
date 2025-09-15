from fastapi import UploadFile
from pathlib import Path
from .config import settings
from .utils.file_safety import safe_extract_zip
from typing import List, Tuple
import os

# Optional Ray import with graceful fallback
try:
    import ray  # type: ignore
    _RAY_AVAILABLE = True
except Exception:
    _RAY_AVAILABLE = False

async def stage_upload(repo_dir: Path, upload: UploadFile) -> Path:
    """Save uploaded zip to disk; return path.

    Uses Ray to parallelize chunk writes when available; falls back to sequential writes otherwise.
    """
    tmp_zip = repo_dir / "upload.zip"
    # Ensure file exists and sized to 0
    tmp_zip.touch()

    # Choose strategy based on Ray availability
    if _RAY_AVAILABLE:
        try:
            if not ray.is_initialized():
                ray.init(ignore_reinit_error=True, logging_level=os.environ.get("RAY_LOG_TO_STDERR", "ERROR"))

            @ray.remote(max_retries=2)
            def _write_chunk(chunk_data: bytes, offset: int, path_str: str) -> int:
                with open(path_str, "r+b") as f:
                    f.seek(offset)
                    f.write(chunk_data)
                return len(chunk_data)

            offset = 0
            futures: List = []
            # Grow file as we go to avoid sparse issues on some FS
            with open(tmp_zip, "r+b") as f:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    # Extend file to accommodate chunk if needed
                    f.seek(offset + len(chunk) - 1)
                    f.write(b"\0")
                    futures.append(_write_chunk.remote(chunk, offset, str(tmp_zip)))
                    offset += len(chunk)
            if futures:
                ray.get(futures)
            
            # Validate the written file
            if tmp_zip.exists() and tmp_zip.stat().st_size > 0:
                return tmp_zip
            else:
                raise ValueError("Incomplete write - retry upload")
        except Exception:
            # Fallback to sequential path if Ray fails mid-way
            pass

    # Sequential fallback
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
