from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timezone
import json
import hashlib
import time

from app.config import settings
from app.parsers.js_ts import parse_js_ts_file
from app.parsers.python import parse_python_file
from app.models import FileNodeModel, ImportModel, FunctionModel, ClassModel, RouteModel, SymbolsModel
from typing import cast

# Optional Ray support
try:
    import ray  # type: ignore
    _RAY_AVAILABLE = True
except Exception:
    _RAY_AVAILABLE = False


def generate_file_blurb(entry: Dict[str, Any]) -> str:
    """Generate a shallow blurb describing the file based on its hints and metadata."""
    hints = entry.get("hints", {})
    symbols = entry.get("symbols", {})
    imports = entry.get("imports", [])
    path = entry.get("path", "")
    
    # Determine file type
    if hints.get("isRoute"):
        file_type = "route"
    elif hints.get("isReactComponent"):
        file_type = "React component"
    elif hints.get("isAPI"):
        file_type = "API endpoint"
    else:
        file_type = "file"
    
    # Add framework context
    framework = hints.get("framework")
    if framework:
        file_type = f"{framework} {file_type}"
    
    # Count internal vs external imports
    internal_imports = [imp for imp in imports if not imp.get("external", True)]
    external_imports = [imp for imp in imports if imp.get("external", True)]
    
    # Build description
    parts = [file_type]
    
    # Add symbol information
    functions = entry.get("functions", [])
    if hasattr(symbols, 'components'):
        # SymbolsModel object
        classes = symbols.components
    else:
        # Dict object (legacy)
        classes = symbols.get("classes", [])
    
    # Add Django models info
    db_models = []
    if hasattr(symbols, 'dbModels'):
        db_models = symbols.dbModels
    elif isinstance(symbols, dict):
        db_models = symbols.get("dbModels", [])
    
    if functions and classes:
        parts.append(f"with {len(functions)} function(s) and {len(classes)} class(es)")
    elif functions:
        parts.append(f"with {len(functions)} function(s)")
    elif classes:
        parts.append(f"with {len(classes)} class(es)")
    
    if db_models:
        parts.append(f"defines {len(db_models)} Django model(s)")
    
    # Add import information
    if internal_imports and external_imports:
        parts.append(f"imports {len(internal_imports)} internal and {len(external_imports)} external modules")
    elif internal_imports:
        parts.append(f"imports {len(internal_imports)} internal module(s)")
    elif external_imports:
        parts.append(f"imports {len(external_imports)} external module(s)")
    
    # Add specific import details for components
    if hints.get("isReactComponent") and internal_imports:
        internal_names = [imp.get("raw", "").split("/")[-1] for imp in internal_imports]
        parts.append(f"imports: {', '.join(internal_names[:3])}")
        if len(internal_names) > 3:
            parts.append(f"and {len(internal_names) - 3} more")
    
    return ". ".join(parts) + "."

LANG_BY_EXT = {
    ".js": "js", ".mjs": "js", ".cjs": "js",
    ".jsx": "js", ".ts": "ts", ".tsx": "ts",
    ".py": "py",
}

# Enhanced ignore patterns for better file discovery
IGNORED_DIRS = {
    "node_modules", ".git", ".svn", ".hg", ".bzr",
    "__pycache__", ".pytest_cache", ".tox", ".venv", "venv", "env",
    "coverage", ".coverage", "htmlcov", ".nyc_output",
    "dist", "build", ".next", ".nuxt", "out",
    "logs", "log", "tmp", "temp", ".tmp", ".temp",
    "migrations", "migration", "alembic", "versions",
    "test", "tests", "__tests__", "spec", "specs",
    ".cache", "cache", ".parcel-cache", ".turbo",
    "docs", "documentation", "examples", "samples",
    "vendor", "third_party", "external"
}

IGNORED_EXTS = {
    ".log", ".tmp", ".temp", ".cache", ".lock", ".pid",
    ".map", ".min.js", ".min.css", ".bundle.js",
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib",
    ".exe", ".bin", ".app", ".deb", ".rpm", ".msi",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".rar", ".dmg", ".iso", ".img",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff",
    ".svg", ".ico", ".webp", ".avif",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".db", ".sqlite", ".sqlite3", ".mdb", ".accdb"
}

def _is_ignored(path: Path) -> bool:
    """Enhanced file ignoring with better patterns."""
    parts = path.parts
    
    # Check for ignored directories
    if any(p in IGNORED_DIRS for p in parts):
        return True
    
    # Check for ignored extensions
    if path.suffix.lower() in IGNORED_EXTS:
        return True
    
    # Check for hidden files (except some important ones)
    if path.name.startswith('.') and path.name not in {'.env', '.gitignore', '.eslintrc', '.prettierrc'}:
        return True
    
    # Check for backup files
    if path.name.endswith(('~', '.bak', '.backup', '.orig')):
        return True
    
    # Check for generated files
    if any(pattern in path.name for pattern in ['generated', 'auto-generated', 'build-']):
        return True
    
    return False


def _compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of file content for caching."""
    try:
        with file_path.open('rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return ""


def _get_file_metadata(file_path: Path) -> Dict[str, Any]:
    """Get comprehensive file metadata."""
    try:
        stat = file_path.stat()
        return {
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "hash": _compute_file_hash(file_path)
        }
    except Exception:
        return {"size": 0, "mtime": 0, "hash": ""}


def resolve_import(import_raw: str, from_file_path: str, snapshot: Path, available_files: List[str]) -> tuple[str | None, bool]:
    """
    Resolve an import to determine if it's internal or external.
    Returns (resolved_path_or_None, external_flag).
    """
    from pathlib import PurePosixPath
    
    # Get top-level directories in the repo
    top_dirs = set()
    for file_path in available_files:
        if "/" in file_path:
            top_dirs.add(file_path.split("/")[0])
    
    # Common roots we often see in projects
    COMMON_ROOTS = [d for d in ["src", "app", "lib", "server", "client", "components", "utils"] if d in top_dirs]
    
    def _try_candidates(candidates: list[str]) -> tuple[str | None, bool]:
        """Return (resolved_path_or_None, external_flag)."""
        for candidate in candidates:
            if candidate in available_files:
                return candidate, False  # internal
        return None, True  # external
    
    def _candidate_with_exts(base_no_ext: str) -> list[str]:
        """Generate candidate paths with various extensions."""
        return [
            base_no_ext,
            base_no_ext + ".ts", base_no_ext + ".tsx", base_no_ext + ".js", base_no_ext + ".jsx",
            base_no_ext + ".py",
            base_no_ext + "/index.ts", base_no_ext + "/index.tsx", base_no_ext + "/index.js", base_no_ext + "/index.jsx",
            base_no_ext + "/__init__.py",
        ]
    
    raw_str = import_raw.strip()
    
    # 1) Relative paths: ./ or ../
    if raw_str.startswith("."):
        base = PurePosixPath(from_file_path).parent
        candidate_no_ext = str((base / raw_str)).replace("\\", "/")
        candidates = _candidate_with_exts(candidate_no_ext)
        return _try_candidates(candidates)
    
    # 2) Leading slash → treat as repo-rooted (strip it)
    if raw_str.startswith("/"):
        raw_str = raw_str.lstrip("/")
    
    # 3) TypeScript alias "@/x" → try src/x and app/x
    if raw_str.startswith("@/"):
        tail = raw_str[2:].lstrip("/")
        candidates = []
        for root in COMMON_ROOTS:
            candidates.extend(_candidate_with_exts(f"{root}/{tail}"))
        return _try_candidates(candidates)
    
    # 4) Rooted path like "src/...", "app/...", "lib/..."
    first_seg = raw_str.split("/")[0]
    if first_seg in COMMON_ROOTS:
        candidates = _candidate_with_exts(raw_str)
        return _try_candidates(candidates)
    
    # 5) Python module style: "pkg.sub.mod" → "pkg/sub/mod"
    if "." in raw_str and "/" not in raw_str:
        py_path = raw_str.replace(".", "/")
        candidates = _candidate_with_exts(py_path)
        for root in top_dirs:
            candidates.extend(_candidate_with_exts(f"{root}/{py_path}"))
        return _try_candidates(candidates)
    
    # 6) Simple module name (no dots) - try with top-level roots
    if "." not in raw_str and "/" not in raw_str and not raw_str.startswith("@"):
        candidates = []
        for root in top_dirs:
            candidates.extend(_candidate_with_exts(f"{root}/{raw_str}"))
        return _try_candidates(candidates)
    
    # 7) If raw contains a slash but didn't match above, still try as repo-rooted
    if "/" in raw_str:
        candidates = _candidate_with_exts(raw_str)
        return _try_candidates(candidates)
    
    # 8) Otherwise treat as external (npm/stdlib/etc.)
    return None, True

def detect_project_context(snapshot: Path) -> Dict[str, Any]:
    """
    Comprehensive project-wide framework detection.
    Detects Next.js, Express, FastAPI, Flask, Django, and other frameworks.
    """
    ctx = {
        "nextjs": False,
        "express": False,
        "koa": False,
        "nestjs": False,
        "fastapi": False,
        "flask": False,
        "django": False,
        "react": False,
        "vue": False,
        "angular": False
    }
    
    # Check package.json for Node.js frameworks
    pkg_json = snapshot / "package.json"
    if not pkg_json.exists():
        pkg_json = snapshot.parent / "package.json"
    
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
            deps = {}
            for k in ("dependencies", "devDependencies", "peerDependencies"):
                v = data.get(k)
                if isinstance(v, dict):
                    deps.update(v)
            
            # Node.js frameworks
            if "next" in deps:
                ctx["nextjs"] = True
            if "express" in deps:
                ctx["express"] = True
            if "koa" in deps:
                ctx["koa"] = True
            if "@nestjs/core" in deps:
                ctx["nestjs"] = True
            
            # Frontend frameworks
            if "react" in deps:
                ctx["react"] = True
            if "vue" in deps:
                ctx["vue"] = True
            if "@angular/core" in deps:
                ctx["angular"] = True
                
        except Exception:
            # ignore malformed package.json
            pass

    # Check requirements.txt for Python frameworks
    req_files = [
        snapshot / "requirements.txt",
        snapshot / "requirements-dev.txt",
        snapshot / "pyproject.toml",
        snapshot.parent / "requirements.txt"
    ]
    
    for req_file in req_files:
        if req_file.exists():
            try:
                content = req_file.read_text(encoding="utf-8", errors="ignore").lower()
                if "fastapi" in content:
                    ctx["fastapi"] = True
                if "flask" in content:
                    ctx["flask"] = True
                if "django" in content:
                    ctx["django"] = True
            except Exception:
                pass

    # Folder heuristics
    if (snapshot / "src" / "app").exists() or (snapshot / "pages").exists():
        ctx["nextjs"] = True
    if (snapshot / "app").exists() and (snapshot / "app" / "main.py").exists():
        ctx["fastapi"] = True
    if (snapshot / "manage.py").exists():
        ctx["django"] = True
    if (snapshot / "app.py").exists() or (snapshot / "flask_app.py").exists():
        ctx["flask"] = True

    return ctx

def iter_all_source_files(repo_root: Path):
    """Iterate over all source files (.py, .js, .ts, .jsx, .tsx), skipping build artifacts."""
    source_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}
    
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
            
        # Skip if not a source file
        if p.suffix.lower() not in source_extensions:
            continue
            
        # Skip virtualenvs, hidden, tests, and build artifacts
        if any(seg.startswith((".", "__pycache__", "venv", "env")) for seg in p.parts):
            continue
        if any(seg in ("node_modules", "dist", "build", ".next", ".nuxt", "out") for seg in p.parts):
            continue
        if "runs/" in str(p.relative_to(repo_root)):
            continue
        if any(seg in ("test", "tests", "__tests__", "spec", "specs") for seg in p.parts):
            continue
            
        yield p

def discover_files(snapshot: Path) -> List[Dict[str, Any]]:
    """Enhanced file discovery with better filtering and metadata."""
    files: List[Dict[str, Any]] = []
    
    for p in snapshot.rglob("*"):
        if not p.is_file():
            continue
        
        # Use enhanced ignore patterns
        if _is_ignored(p.relative_to(snapshot)):
            continue
        
        try:
            # Get comprehensive metadata
            metadata = _get_file_metadata(p)
            size = metadata["size"]
            
            # Check file size limits
            if size > settings.MAX_FILE_MB * 1024 * 1024:
                files.append({
                    "path": str(p.relative_to(snapshot)).replace("\\", "/"),
                    "ext": p.suffix.lower(),
                    "language": LANG_BY_EXT.get(p.suffix.lower(), "other"),
                    "size": size,
                    "lines": None,
                    "skipped": True,
                    "skipReason": "file_too_large_for_parse",
                    "hash": metadata["hash"],
                    "mtime": metadata["mtime"]
                })
                continue
            
            # Count lines (best-effort)
            try:
                with p.open("rb") as f:
                    lines = sum(1 for _ in f)
            except Exception:
                lines = None
            
            files.append({
                "path": str(p.relative_to(snapshot)).replace("\\", "/"),
                "ext": p.suffix.lower(),
                "language": LANG_BY_EXT.get(p.suffix.lower(), "other"),
                "size": size,
                "lines": lines,
                "skipped": False,
                "hash": metadata["hash"],
                "mtime": metadata["mtime"]
            })
            
        except Exception:
            files.append({
                "path": str(p.relative_to(snapshot)).replace("\\", "/"),
                "ext": p.suffix.lower(),
                "language": LANG_BY_EXT.get(p.suffix.lower(), "other"),
                "size": None,
                "lines": None,
                "skipped": True,
                "skipReason": "stat_failed",
                "hash": "",
                "mtime": 0
            })
    
    return files

def _load_parse_cache(cache_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load cached parse results."""
    if not cache_path.exists():
        return {}
    
    try:
        with cache_path.open('r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_parse_cache(cache_path: Path, cache_data: Dict[str, Dict[str, Any]]) -> None:
    """Save parse results to cache."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Convert SymbolsModel objects to dicts for JSON serialization
        serializable_cache = {}
        for file_path, entry in cache_data.items():
            serializable_entry = entry.copy()
            if hasattr(entry.get("symbols"), "model_dump"):
                # Convert SymbolsModel to dict
                serializable_entry["symbols"] = entry["symbols"].model_dump()
            serializable_cache[file_path] = serializable_entry
        
        with cache_path.open('w', encoding='utf-8') as f:
            json.dump(serializable_cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _should_reparse_file(file_meta: Dict[str, Any], cached_entry: Optional[Dict[str, Any]]) -> bool:
    """Determine if a file needs to be reparsed based on cache."""
    if not cached_entry:
        return True
    
    # Check if file hash changed
    cached_hash = cached_entry.get("hash", "")
    current_hash = file_meta.get("hash", "")
    if cached_hash != current_hash:
        return True
    
    # Check if file was modified recently (within last hour)
    cached_mtime = cached_entry.get("mtime", 0)
    current_mtime = file_meta.get("mtime", 0)
    if abs(current_mtime - cached_mtime) > 3600:  # 1 hour
        return True
    
    return False


def _validate_and_normalize_file_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize a file entry against FileNodeModel schema."""
    try:
        # Convert old symbols format to new SymbolsModel
        if "symbols" in entry and isinstance(entry["symbols"], dict):
            old_symbols = entry["symbols"]
            entry["symbols"] = SymbolsModel(
                constants=old_symbols.get("constants", []),
                hooks=old_symbols.get("hooks", []),
                dbModels=old_symbols.get("dbModels", []),
                middleware=old_symbols.get("middleware", []),
                components=old_symbols.get("components", []),
                utilities=old_symbols.get("utilities", [])
            )
        elif "symbols" not in entry:
            # Initialize symbols if not present
            entry["symbols"] = SymbolsModel()
        
        # Ensure all required fields are present with defaults
        normalized = {
            "path": entry.get("path", ""),
            "language": entry.get("language", "other"),
            "ext": entry.get("ext", ""),
            "exports": entry.get("exports", []),
            "imports": entry.get("imports", []),
            "functions": entry.get("functions", []),
            "classes": entry.get("classes", []),
            "routes": entry.get("routes", []),
            "symbols": entry.get("symbols", SymbolsModel()),
            "hints": entry.get("hints", {}),
            "warnings": entry.get("warnings", []),
            "blurb": entry.get("blurb", ""),
            "skipped": entry.get("skipped", False),
            "skipReason": entry.get("skipReason"),
            "size": entry.get("size", 0),
            "lines": entry.get("lines"),
            "hash": entry.get("hash", ""),
            "mtime": entry.get("mtime", 0)
        }
        
        # Validate against FileNodeModel (this will raise ValidationError if invalid)
        FileNodeModel(**normalized)
        
        return normalized
        
    except Exception as e:
        # If validation fails, return a minimal valid entry
        return {
            "path": entry.get("path", ""),
            "language": entry.get("language", "other"),
            "ext": entry.get("ext", ""),
            "exports": [],
            "imports": [],
            "functions": [],
            "classes": [],
            "routes": [],
            "symbols": SymbolsModel(),
            "hints": {},
            "warnings": [f"Schema validation failed: {str(e)}"],
            "blurb": "Invalid file entry",
            "skipped": True,
            "skipReason": "validation_failed",
            "size": entry.get("size", 0),
            "lines": entry.get("lines"),
            "hash": entry.get("hash", ""),
            "mtime": entry.get("mtime", 0)
        }


def parse_files(snapshot: Path, discovered: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Enhanced file parsing with caching and incremental updates.

    Uses Ray to parallelize parsing when available, with a safe sequential fallback.
    """
    import time
    import logging
    
    logger = logging.getLogger(__name__)
    start_time = time.time()
    warnings: List[str] = []
    out: List[Dict[str, Any]] = []
    
    # Load parse cache
    cache_path = snapshot / "parse_cache.json"
    cache = _load_parse_cache(cache_path)
    cache_updated = False
    
    # Clean up cache entries for files that no longer exist
    discovered_paths = {meta["path"] for meta in discovered}
    cached_paths = set(cache.keys())
    deleted_paths = cached_paths - discovered_paths
    
    if deleted_paths:
        for deleted_path in deleted_paths:
            del cache[deleted_path]
            cache_updated = True
            warnings.append(f"Removed cache entry for deleted file: {deleted_path}")
    
    # Detect repo-wide framework context once
    ctx = detect_project_context(snapshot)

    # Determine which files need reparsing
    to_reparse: List[Dict[str, Any]] = []
    for meta in discovered:
        file_path_str = meta["path"]
        cached_entry = cache.get(file_path_str)
        if _should_reparse_file(meta, cached_entry):
            to_reparse.append(meta)

    # Common inputs
    available_files = [f["path"] for f in discovered if not f.get("skipped", False)]

    # Ray-parallel path
    results_by_path: Dict[str, Dict[str, Any]] = {}
    if _RAY_AVAILABLE and to_reparse:
        try:
            if not ray.is_initialized():
                ray.init(ignore_reinit_error=True, logging_level="ERROR")

            @ray.remote(num_cpus=1, max_retries=2)
            def _process_batch(metas: List[Dict[str, Any]], snapshot_str: str, available: List[str], ctx_in: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
                batch_out: List[Dict[str, Any]] = []
                batch_warnings: List[str] = []
                snap = Path(snapshot_str)
                for meta in metas:
                    entry = {
                        "path": meta["path"],
                        "language": meta["language"],
                        "ext": meta["ext"],
                        "size": meta["size"],
                        "lines": meta["lines"],
                        "hash": meta.get("hash", ""),
                        "mtime": meta.get("mtime", 0),
                        "symbols": SymbolsModel(),
                        "imports": [],
                        "exports": [],
                        "routes": [],
                        "hints": {"framework": None, "isRoute": False, "isReactComponent": False, "isAPI": False},
                        "warnings": [],
                    }
                    try:
                        if meta.get("skipped"):
                            entry["warnings"].append(f"Skipped {meta['path']} due to {meta.get('skipReason','unknown')}.")
                        else:
                            file_path = snap / meta["path"]
                            lang = meta["language"]
                            if lang in ("js", "ts"):
                                parsed = parse_js_ts_file(file_path, entry["ext"], snap, available)
                            elif lang == "py":
                                parsed = parse_python_file(file_path, snap, available)
                            else:
                                parsed = {"imports": [], "exports": [], "functions": [], "classes": [], "routes": [], "symbols": {}, "hints": {}}
                            entry["imports"] = parsed.get("imports", [])
                            entry["exports"] = parsed.get("exports", [])
                            entry["functions"] = parsed.get("functions", [])
                            entry["classes"] = parsed.get("classes", [])
                            entry["routes"] = parsed.get("routes", [])
                            parsed_symbols = parsed.get("symbols", {})
                            if isinstance(parsed_symbols, dict):
                                entry["symbols"] = SymbolsModel(
                                    constants=parsed_symbols.get("constants", []),
                                    hooks=parsed_symbols.get("hooks", []),
                                    dbModels=parsed_symbols.get("dbModels", []),
                                    middleware=parsed_symbols.get("middleware", []),
                                    components=parsed_symbols.get("components", []),
                                    utilities=parsed_symbols.get("utilities", [])
                                )
                            else:
                                entry["symbols"] = parsed_symbols
                            hints = parsed.get("hints", {})
                            entry["hints"].update({k: v for k, v in hints.items() if v is not None})
                            if ctx_in.get("nextjs") and entry["hints"].get("framework") is None and entry["ext"] in (".tsx", ".jsx"):
                                entry["hints"]["framework"] = "nextjs"
                    except Exception as e:  # noqa: BLE001
                        msg = f"Parse failed for {meta['path']}: {e}"
                        entry["warnings"].append(msg)
                        batch_warnings.append(msg)
                    # blurb + validate
                    entry["blurb"] = generate_file_blurb(entry)
                    entry = _validate_and_normalize_file_entry(entry)
                    batch_out.append(entry)
                return batch_out, batch_warnings

            # Configurable batch size via environment variable
            import os
            batch_size = int(os.getenv('BATCH_SIZE', 50))
            batches = [to_reparse[i:i + batch_size] for i in range(0, len(to_reparse), batch_size)]
            futures = [_process_batch.remote(batch, str(snapshot), available_files, ctx) for batch in batches]
            
            # Process results with per-batch error handling
            for fut in futures:
                try:
                    batch_out, batch_warn = ray.get(fut)
                    warnings.extend(batch_warn)
                    for entry in batch_out:
                        results_by_path[entry["path"]] = entry
                        cache[entry["path"]] = entry
                except Exception as e:
                    # Log batch failure but don't crash - create fallback entries
                    batch_warning = f"Batch processing failed: {e}"
                    warnings.append(batch_warning)
                    # Create minimal fallback entries for failed batch
                    for meta in batches[futures.index(fut)]:
                        fallback_entry = {
                            "path": meta["path"],
                            "language": meta["language"],
                            "ext": meta["ext"],
                            "size": meta["size"],
                            "lines": meta["lines"],
                            "hash": meta.get("hash", ""),
                            "mtime": meta.get("mtime", 0),
                            "symbols": SymbolsModel(),
                            "imports": [],
                            "exports": [],
                            "routes": [],
                            "hints": {"framework": None, "isRoute": False, "isReactComponent": False, "isAPI": False},
                            "warnings": [f"Batch processing failed: {e}"],
                            "blurb": f"File {meta['path']} (processing failed)"
                        }
                        fallback_entry = _validate_and_normalize_file_entry(fallback_entry)
                        results_by_path[meta["path"]] = fallback_entry
                        cache[meta["path"]] = fallback_entry
            
            # Explicit Ray shutdown for cleanup
            ray.shutdown()
            cache_updated = True
        except Exception:
            # Fall back to sequential path
            results_by_path = {}

    # Sequential path for any remaining files or when Ray is unavailable
    if not results_by_path and to_reparse:
        for meta in to_reparse:
            file_path_str = meta["path"]
            # Parse the file
            entry = {
                "path": meta["path"],
                "language": meta["language"],
                "ext": meta["ext"],
                "size": meta["size"],
                "lines": meta["lines"],
                "hash": meta.get("hash", ""),
                "mtime": meta.get("mtime", 0),
                "symbols": SymbolsModel(),
                "imports": [],
                "exports": [],
                "routes": [],
                "hints": {"framework": None, "isRoute": False, "isReactComponent": False, "isAPI": False},
                "warnings": [],
            }
            if meta.get("skipped"):
                entry["warnings"].append(f"Skipped {meta['path']} due to {meta.get('skipReason','unknown')}.")
            else:
                file_path = snapshot / meta["path"]
                lang = meta["language"]
                try:
                    if lang in ("js", "ts"):
                        parsed = parse_js_ts_file(file_path, entry["ext"], snapshot, available_files)
                    elif lang == "py":
                        parsed = parse_python_file(file_path, snapshot, available_files)
                    else:
                        parsed = {"imports": [], "exports": [], "functions": [], "classes": [], "routes": [], "symbols": {}, "hints": {}}
                    entry["imports"] = parsed.get("imports", [])
                    entry["exports"] = parsed.get("exports", [])
                    entry["functions"] = parsed.get("functions", [])
                    entry["classes"] = parsed.get("classes", [])
                    entry["routes"] = parsed.get("routes", [])
                    parsed_symbols = parsed.get("symbols", {})
                    if isinstance(parsed_symbols, dict):
                        entry["symbols"] = SymbolsModel(
                            constants=parsed_symbols.get("constants", []),
                            hooks=parsed_symbols.get("hooks", []),
                            dbModels=parsed_symbols.get("dbModels", []),
                            middleware=parsed_symbols.get("middleware", []),
                            components=parsed_symbols.get("components", []),
                            utilities=parsed_symbols.get("utilities", [])
                        )
                    else:
                        entry["symbols"] = parsed_symbols
                    hints = parsed.get("hints", {})
                    entry["hints"].update({k: v for k, v in hints.items() if v is not None})
                    if ctx.get("nextjs") and entry["hints"].get("framework") is None and entry["ext"] in (".tsx", ".jsx"):
                        entry["hints"]["framework"] = "nextjs"
                except Exception as e:
                    msg = f"Parse failed for {meta['path']}: {e}"
                    entry["warnings"].append(msg)
                    warnings.append(msg)
            entry["blurb"] = generate_file_blurb(entry)
            entry = _validate_and_normalize_file_entry(entry)
            results_by_path[file_path_str] = entry
            cache[file_path_str] = entry
            cache_updated = True

    # Build output in discovered order, mixing in cached entries where appropriate
    for meta in discovered:
        file_path_str = meta["path"]
        if file_path_str in results_by_path:
            out.append(results_by_path[file_path_str])
        else:
            cached_entry = cache.get(file_path_str)
            if cached_entry:
                out.append(_validate_and_normalize_file_entry(cached_entry.copy()))
            else:
                # Should not happen; produce minimal entry
                out.append(_validate_and_normalize_file_entry({"path": file_path_str, "language": meta.get("language", "other")}))
    
    # Save updated cache
    if cache_updated:
        _save_parse_cache(cache_path, cache)
    
    # Log timing metrics
    parse_time = time.time() - start_time
    logger.info(f"Parsed {len(out)} files in {parse_time:.2f}s using {'Ray' if _RAY_AVAILABLE else 'sequential'} processing")
    
    return out, warnings

def build_files_payload(repo_id: str, files_list: List[Dict[str, Any]], top_warnings: List[str]) -> Dict[str, Any]:
    """Build the final files payload with unified schema compliance."""
    # Normalize files to unified schema
    normalized_files = []
    for f in files_list:
        # Ensure all required fields are present
        normalized_file = {
            "path": f.get("path", ""),
            "language": f.get("language", "other"),
            "ext": f.get("ext", ""),
            "size": f.get("size", 0),
            "lines": f.get("lines"),
            "hash": f.get("hash", ""),
            "mtime": f.get("mtime", 0),
            "imports": f.get("imports", []),
            "exports": f.get("exports", []),
            "functions": f.get("functions", []),
            "classes": f.get("classes", []),
            "routes": f.get("routes", []),
            "symbols": f.get("symbols", {}),
            "hints": f.get("hints", {}),
            "warnings": f.get("warnings", []),
            "blurb": f.get("blurb", ""),
            "skipped": f.get("skipped", False),
            "skipReason": f.get("skipReason")
        }
        
        # Backward compatibility: move old functionTags to new structure
        if "functionTags" in f:
            for func in normalized_file["functions"]:
                if isinstance(func, dict) and "name" in func:
                    # Find matching function in functionTags
                    for tag in f["functionTags"]:
                        if tag.get("name") == func["name"]:
                            func["sideEffects"] = tag.get("sideEffects", [])
                            break
        
        normalized_files.append(normalized_file)
    
    # Count languages
    lang_counts: Dict[str, int] = {}
    for f in normalized_files:
        lang = f.get("language", "other")
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
    
    payload = {
        "repoId": repo_id,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "totalFiles": len(normalized_files),
            "languages": lang_counts
        },
        "files": normalized_files,
        "warnings": top_warnings,
    }
    return payload

def build_graph(files_payload: Dict[str, Any]) -> Dict[str, Any]:
    # Build nodes keyed by posix path (exactly as stored in files.json)
    nodes = {f["path"]: {"id": f["path"], "inDegree": 0, "outDegree": 0} for f in files_payload["files"]}

    # Heuristic roots present in this repo (derive from existing node paths)
    top_dirs = set(p.split("/")[0] for p in nodes.keys() if "/" in p)
    # Common roots we often see in JS/TS apps; we'll try these if present
    COMMON_ROOTS = [d for d in ["src", "app", "lib", "server", "client"] if d in top_dirs]

    def _try_candidates(cands: list[str]) -> tuple[str | None, bool]:
        """Return (resolved_path_or_None, external_flag)."""
        for c in cands:
            if c in nodes:
                return c, False  # internal
        return None, True      # still looks external

    def _candidate_with_exts(base_no_ext: str) -> list[str]:
        return [
            base_no_ext,
            base_no_ext + ".ts", base_no_ext + ".tsx", base_no_ext + ".js", base_no_ext + ".jsx", base_no_ext + ".py",
            base_no_ext + "/index.ts", base_no_ext + "/index.tsx", base_no_ext + "/index.js", base_no_ext + "/index.jsx",
            base_no_ext + "/__init__.py",  # python package (prefer module.py over module/__init__.py)
        ]

    def resolve(from_path: str, raw: str) -> tuple[str | None, bool]:
        """Best-effort resolver:
        - relative ('./', '../')
        - root-ish ('src/...', 'app/...', '/src/...', '@/...')
        - python module ('pkg.mod.sub') or bare ('name')
        Returns (resolved_path or None, external_flag).
        """
        from pathlib import PurePosixPath

        raw_str = raw.strip()
        # 1) Relative paths: ./ or ../
        if raw_str.startswith("."):
            base = PurePosixPath(from_path).parent
            candidate_no_ext = str((base / raw_str)).replace("\\", "/")
            cands = _candidate_with_exts(candidate_no_ext)
            return _try_candidates(cands)

        # 2) Leading slash → treat as repo-rooted (strip it)
        if raw_str.startswith("/"):
            raw_str = raw_str.lstrip("/")

        # 3) TS alias "@/x" → try src/x and app/x (if those roots exist)
        alias_cands: list[str] = []
        if raw_str.startswith("@/"):
            tail = raw_str[2:].lstrip("/")
            for root in [r for r in ["src", "app"] if r in top_dirs] or ["src", "app"]:
                alias_cands.extend(_candidate_with_exts(f"{root}/{tail}"))

        # 4) Rooted path like "src/...", "app/...", "lib/..." (only try if that root exists)
        rooted_cands: list[str] = []
        first_seg = raw_str.split("/")[0]
        if first_seg in COMMON_ROOTS:
            rooted_cands.extend(_candidate_with_exts(raw_str))

        # 5) Python module style: "pkg.sub.mod" → "pkg/sub/mod" (try at each top-level root)
        py_cands: list[str] = []
        if "." in raw_str and "/" not in raw_str:
            py_path = raw_str.replace(".", "/")
            py_cands.extend(_candidate_with_exts(py_path))
            for root in top_dirs:
                py_cands.extend(_candidate_with_exts(f"{root}/{py_path}"))
        
        # 5b) Simple module name (no dots) - try with top-level roots
        simple_cands: list[str] = []
        if "." not in raw_str and "/" not in raw_str and not raw_str.startswith("@"):
            for root in top_dirs:
                simple_cands.extend(_candidate_with_exts(f"{root}/{raw_str}"))

        # 6) If raw contains a slash but didn't match above, still try as repo-rooted
        generic_cands: list[str] = []
        if "/" in raw_str:
            generic_cands.extend(_candidate_with_exts(raw_str))

        # Try in priority order
        for group in (alias_cands, rooted_cands, py_cands, simple_cands, generic_cands):
            resolved, external = _try_candidates(group)
            if resolved:
                return resolved, external

        # 7) Otherwise treat as external (npm/stdlib/etc.)
        return None, True

    edges = []
    warnings = []
    for f in files_payload["files"]:
        frm = f["path"]
        for imp in f.get("imports", []):
            raw = imp.get("raw")
            if not raw:
                continue
            resolved, external = resolve(frm, raw)
            # Prefer resolved internal path when available
            edge_to = resolved or raw
            edge = {"from": frm, "to": edge_to, "external": external}
            if resolved:
                edge["resolved"] = resolved
                # bump degrees for internal link
                nodes[frm]["outDegree"] += 1
                nodes[resolved]["inDegree"] += 1
            else:
                # Looks like a local-ish import but couldn’t resolve → helpful warning
                raw_str = raw.strip()
                if (
                    raw_str.startswith(".")
                    or raw_str.startswith("/")
                    or raw_str.startswith("@/")
                    or (raw_str.startswith(("src/", "app", "lib/", "server/", "client/")) and "/" in raw_str)
                    or ("." in raw_str and "/" not in raw_str)  # python dotted import
                ):
                    warnings.append(f"Unresolved local import '{raw}' in {frm}")
            edges.append(edge)

    top_hubs = sorted(nodes.values(), key=lambda n: (n["inDegree"] + n["outDegree"]), reverse=True)[:10]
    return {
        "repoId": files_payload["repoId"],
        "generatedAt": files_payload["generatedAt"],
        "nodes": list(nodes.values()),
        "edges": edges,
        "warnings": warnings,
        "metrics": {
            "numNodes": len(nodes),
            "numEdges": len(edges),
            "topHubs": [n["id"] for n in top_hubs],
        },
    }
