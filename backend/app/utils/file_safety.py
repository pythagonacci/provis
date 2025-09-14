from pathlib import Path
from zipfile import ZipFile
from typing import Iterable
import os

class ZipTooLargeError(Exception): pass
class FileCountExceeded(Exception): pass
class FileTooLargeError(Exception): pass
class UnsafePathError(Exception): pass

def _is_within_directory(directory: Path, target: Path) -> bool:
    try:
        directory = directory.resolve(strict=False)
        target = target.resolve(strict=False)
        return os.path.commonpath([str(directory)]) == os.path.commonpath([str(directory), str(target)])
    except Exception:
        return False

def safe_extract_zip(zip_path: Path, dest: Path, *,
                     max_zip_bytes: int,
                     max_files: int,
                     max_file_bytes: int,
                     ignored_dirs: Iterable[str],
                     ignored_exts: Iterable[str]) -> int:
    """Extract zip with safety checks. Returns count of files written."""
    if zip_path.stat().st_size > max_zip_bytes:
        raise ZipTooLargeError(f"Zip exceeds {max_zip_bytes} bytes")

    count = 0
    dest.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path) as z:
        infos = z.infolist()
        if len(infos) > max_files:
            raise FileCountExceeded(f"Archive has {len(infos)} entries > max {max_files}")
        for info in infos:
            if info.is_dir():
                continue

            # Skip ignored directories and extensions BEFORE size checks
            parts = Path(info.filename).parts
            if any(p in ignored_dirs for p in parts):
                continue
            if Path(info.filename).suffix.lower() in set(ignored_exts):
                continue

            # Enforce per-file size after we know it's worth extracting
            if info.file_size > max_file_bytes:
                raise FileTooLargeError(f"Entry {info.filename} exceeds per-file cap")

            target_path = dest / info.filename
            if not _is_within_directory(dest, target_path.parent):
                raise UnsafePathError(f"Unsafe path: {info.filename}")

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target_path, "wb") as out:
                out.write(src.read())
            count += 1
    return count
