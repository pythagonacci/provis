from pathlib import Path
from zipfile import ZipFile, ZipInfo
import pytest

from app.utils.file_safety import (
    safe_extract_zip,
    ZipTooLargeError,
    FileCountExceeded,
    FileTooLargeError,
    UnsafePathError,
)

def make_zip(tmp_path: Path, files: dict[str, bytes]) -> Path:
    zpath = tmp_path / "sample.zip"
    with ZipFile(zpath, "w") as z:
        for name, data in files.items():
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            z.write(p, arcname=name)
    return zpath

def test_safe_extract_ok(tmp_path: Path):
    z = make_zip(tmp_path, {"src/index.js": b"console.log(1);"})
    out = tmp_path / "out"
    n = safe_extract_zip(
        z, out,
        max_zip_bytes=1_000_000,
        max_files=10,
        max_file_bytes=100_000,
        ignored_dirs=("node_modules",),
        ignored_exts=(".png",),
    )
    assert n == 1
    assert (out / "src/index.js").exists()

def test_ignored_dirs_and_exts(tmp_path: Path):
    z = make_zip(
        tmp_path,
        {"node_modules/lib.js": b"ignored", "assets/logo.png": b"img", "src/app.ts": b"ok"},
    )
    out = tmp_path / "out"
    n = safe_extract_zip(
        z, out,
        max_zip_bytes=1_000_000,
        max_files=100,
        max_file_bytes=100_000,
        ignored_dirs=("node_modules",),
        ignored_exts=(".png",),
    )
    assert n == 1
    assert (out / "src/app.ts").exists()

def test_zip_slip_blocked(tmp_path: Path):
    zpath = tmp_path / "slip.zip"
    with ZipFile(zpath, "w") as z:
        info = ZipInfo("../evil.txt")
        z.writestr(info, "bad")
    out = tmp_path / "out"
    with pytest.raises(UnsafePathError):
        safe_extract_zip(
            zpath, out,
            max_zip_bytes=1_000_000,
            max_files=10,
            max_file_bytes=100_000,
            ignored_dirs=(),
            ignored_exts=(),
        )

def test_zip_too_large(tmp_path: Path):
    z = make_zip(tmp_path, {"a.txt": b"hi"})
    out = tmp_path / "out"
    with pytest.raises(ZipTooLargeError):
        safe_extract_zip(
            z, out,
            max_zip_bytes=1,
            max_files=10,
            max_file_bytes=100_000,
            ignored_dirs=(),
            ignored_exts=(),
        )

def test_file_count_exceeded(tmp_path: Path):
    z = make_zip(tmp_path, {"a.txt": b"a", "b.txt": b"b"})
    out = tmp_path / "out"
    with pytest.raises(FileCountExceeded):
        safe_extract_zip(
            z, out,
            max_zip_bytes=1_000_000,
            max_files=1,
            max_file_bytes=100_000,
            ignored_dirs=(),
            ignored_exts=(),
        )

def test_file_too_large(tmp_path: Path):
    big = b"x" * 20_000
    z = make_zip(tmp_path, {"big.bin": big})
    out = tmp_path / "out"
    with pytest.raises(FileTooLargeError):
        safe_extract_zip(
            z, out,
            max_zip_bytes=1_000_000,
            max_files=10,
            max_file_bytes=10_000,
            ignored_dirs=(),
            ignored_exts=(),
        )
