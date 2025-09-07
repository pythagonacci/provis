from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Tuple
from datetime import datetime, timezone
import json

from app.config import settings
from app.parsers.js_ts import parse_js_ts_file
from app.parsers.python import parse_python_file


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
    functions = symbols.get("functions", [])
    classes = symbols.get("classes", [])
    
    if functions and classes:
        parts.append(f"with {len(functions)} function(s) and {len(classes)} class(es)")
    elif functions:
        parts.append(f"with {len(functions)} function(s)")
    elif classes:
        parts.append(f"with {len(classes)} class(es)")
    
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
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".py": "python",
}

def _is_ignored(path: Path) -> bool:
    parts = path.parts
    if any(p in settings.IGNORED_DIRS for p in parts):
        return True
    if path.suffix.lower() in set(settings.IGNORED_EXTS):
        return True
    return False

def detect_project_context(snapshot: Path) -> Dict[str, Any]:
    """
    Lightweight project-wide signals.
    - nextjs: package.json has 'next' or app/pages folders exist.
    """
    ctx = {"nextjs": False}
    # Try package.json at snapshot root and parent (covers repos zipped at root vs subdir)
    pkg_json = snapshot / "package.json"
    if not pkg_json.exists():
        pkg_json = snapshot.parent / "package.json"
    try:
        if pkg_json.exists():
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
            deps = {}
            for k in ("dependencies", "devDependencies", "peerDependencies"):
                v = data.get(k)
                if isinstance(v, dict):
                    deps.update(v)
            if "next" in deps:
                ctx["nextjs"] = True
    except Exception:
        # ignore malformed package.json
        pass

    # Folder heuristics
    if (snapshot / "src" / "app").exists() or (snapshot / "pages").exists():
        ctx["nextjs"] = True or ctx["nextjs"]

    return ctx

def discover_files(snapshot: Path) -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    for p in snapshot.rglob("*"):
        if not p.is_file():
            continue
        if _is_ignored(p.relative_to(snapshot)):
            continue
        try:
            size = p.stat().st_size
            if size > settings.MAX_FILE_MB * 1024 * 1024:
                files.append({
                    "path": str(p.relative_to(snapshot)).replace("\\", "/"),
                    "ext": p.suffix.lower(),
                    "language": LANG_BY_EXT.get(p.suffix.lower(), "other"),
                    "size": size,
                    "lines": None,
                    "skipped": True,
                    "skipReason": "file_too_large_for_parse"
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
            })
    return files

def parse_files(snapshot: Path, discovered: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return (files_list, warnings). Each entry in files_list has imports/exports/symbols/hints."""
    warnings: List[str] = []
    out: List[Dict[str, Any]] = []

    # Detect repo-wide framework context once
    ctx = detect_project_context(snapshot)

    for meta in discovered:
        entry = {
            "path": meta["path"],
            "language": meta["language"],
            "ext": meta["ext"],
            "size": meta["size"],
            "lines": meta["lines"],
            "symbols": {"functions": [], "classes": []},
            "imports": [],
            "exports": [],
            "hints": {"framework": None, "isRoute": False, "isReactComponent": False, "isAPI": False},
            "warnings": [],
        }

        if meta.get("skipped"):
            entry["warnings"].append(f"Skipped {meta['path']} due to {meta.get('skipReason','unknown')}.")
            entry["blurb"] = generate_file_blurb(entry)
            out.append(entry)
            continue

        file_path = snapshot / meta["path"]
        lang = meta["language"]

        try:
            if lang in ("javascript", "typescript"):
                parsed = parse_js_ts_file(file_path, entry["ext"])
            elif lang == "python":
                parsed = parse_python_file(file_path)
            else:
                parsed = {"imports": [], "exports": [], "symbols": {"functions": [], "classes": []}, "hints": {}}

            # Merge parsed results
            entry["imports"] = parsed.get("imports", [])
            entry["exports"] = parsed.get("exports", [])
            sym = parsed.get("symbols", {})
            entry["symbols"]["functions"] = sym.get("functions", [])
            entry["symbols"]["classes"] = sym.get("classes", [])
            hints = parsed.get("hints", {})
            entry["hints"].update({k: v for k, v in hints.items() if v is not None})

            # --- Project context inheritance ---
            # If the project is Next.js, mark TSX/JSX files with framework=nextjs
            # (do not overwrite explicit hints coming from the parser, e.g., route files)
            if ctx.get("nextjs") and entry["hints"].get("framework") is None and entry["ext"] in (".tsx", ".jsx"):
                entry["hints"]["framework"] = "nextjs"

        except Exception as e:
            msg = f"Parse failed for {meta['path']}: {e}"
            entry["warnings"].append(msg)
            warnings.append(msg)

        # Generate shallow blurb using hints
        entry["blurb"] = generate_file_blurb(entry)
        
        out.append(entry)

    return out, warnings

def build_files_payload(repo_id: str, files_list: List[Dict[str, Any]], top_warnings: List[str]) -> Dict[str, Any]:
    lang_counts: Dict[str, int] = {}
    for f in files_list:
        lang = f.get("language", "other")
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
    payload = {
        "repoId": repo_id,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "totalFiles": len(files_list),
            "languages": lang_counts
        },
        "files": files_list,
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
            edge = {"from": frm, "to": raw, "external": external}
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
