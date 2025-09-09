from __future__ import annotations
from pathlib import Path
import re
from typing import Dict, Any

# ESM imports: import X from "mod"  | import {X} from "mod" | import "mod"
RE_IMPORT = re.compile(r'^\s*import\s+(?:[^"\']+from\s+)?[\'"]([^\'"]+)[\'"]', re.MULTILINE)

# CommonJS require: const x = require("mod")
RE_REQUIRE = re.compile(r'require\(\s*[\'"]([^\'"]+)[\'"]\s*\)')

# Exports (coarse)
RE_EXPORT_DEFAULT = re.compile(r'^\s*export\s+default\b', re.MULTILINE)
RE_EXPORT_ANY = re.compile(r'^\s*export\s+(?:default|const|let|var|function|class)\b', re.MULTILINE)

# Named function/class declarations
RE_FUNC = re.compile(r'^\s*(?:export\s+)?function\s+([A-Za-z0-9_]+)\s*\(', re.MULTILINE)
RE_CLASS = re.compile(r'^\s*(?:export\s+)?class\s+([A-Za-z0-9_]+)\s*', re.MULTILINE)

# Arrow function declarations (captures identifier before '=')
RE_ARROW_DECL = re.compile(
    r'^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_]+)\s*'
    r'(?:\s*:\s*[^=]+)?=\s*(?:async\s*)?\(?[A-Za-z0-9_,\s{}:*=\[\]\.]*\)?\s*=>',
    re.MULTILINE
)

# Default-exported anonymous function/arrow with JSX
RE_DEFAULT_ANON_FUNC = re.compile(
    r'^\s*export\s+default\s+(?:async\s+)?(?:function\s*\(|\(?[A-Za-z0-9_,\s{}:*=\[\]\.]*\)?\s*=>)',
    re.MULTILINE
)

# JSX presence (either explicit return or any tag literal)
RE_RETURNS_JSX = re.compile(r'return\s*<', re.MULTILINE)
RE_JSX_LITERAL = re.compile(r'<[A-Za-z]', re.MULTILINE)


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return p.read_text(encoding="latin-1", errors="ignore")


def _is_pascal(name: str) -> bool:
    return bool(name) and name[0].isupper()


def _detect_framework_hints(path: str, text: str, ext: str) -> Dict[str, Any]:
    hints = {"framework": None, "isRoute": False, "isReactComponent": False, "isAPI": False}

    # Next.js App/Pages router heuristics
    if "/pages/" in path or "/app/" in path:
        hints["framework"] = "nextjs"
        hints["isRoute"] = True
        if "/pages/api/" in path:
            hints["isAPI"] = True

    # React component heuristic for TSX/JSX:
    if ext in (".tsx", ".jsx"):
        has_jsx = bool(RE_RETURNS_JSX.search(text) or RE_JSX_LITERAL.search(text))
        func_names = RE_FUNC.findall(text)
        class_names = RE_CLASS.findall(text)
        arrow_names = RE_ARROW_DECL.findall(text)
        has_default_export = bool(RE_EXPORT_DEFAULT.search(text))

        if has_jsx and (
            has_default_export
            or any(_is_pascal(n) for n in func_names + class_names + arrow_names)
        ):
            hints["isReactComponent"] = True

    return hints


def parse_js_ts_file(p: Path, ext: str) -> Dict[str, Any]:
    text = _read_text(p)

    # Imports
    imports = [{"raw": m, "kind": "esm"} for m in RE_IMPORT.findall(text)]
    for m in RE_REQUIRE.findall(text):
        imports.append({"raw": m, "kind": "cjs"})

    # Exports
    exports = []
    if RE_EXPORT_ANY.search(text):
        exports.append("default" if RE_EXPORT_DEFAULT.search(text) else "named")

    # Symbols (shallow)
    functions = RE_FUNC.findall(text)
    classes = RE_CLASS.findall(text)
    # Arrow-declared identifiers count as "functions" for symbol listing
    for n in RE_ARROW_DECL.findall(text):
        if n not in functions:
            functions.append(n)

    hints = _detect_framework_hints(str(p).replace("\\", "/"), text, ext)
    # Heuristic function side-effects tagging
    def _side_effects(src: str) -> list[str]:
        tags: list[str] = []
        lower = src.lower()
        # net
        if re.search(r"\b(fetch|axios|http\.request|xmlhttprequest|websocket)\b", lower):
            tags.append("net")
        # io
        if re.search(r"\b(fs\.|readfile|writefile|stream|blob)\b", lower):
            tags.append("io")
        # db (common libs)
        if re.search(r"\b(prisma|mongoose|mongodb|pg\.|knex|sequelize)\b", lower):
            tags.append("db")
        # dom/render
        if ext in (".tsx", ".jsx") and (RE_JSX_LITERAL.search(src) or RE_RETURNS_JSX.search(src)):
            tags.append("render")
        return list(dict.fromkeys(tags))

    # Attach sideEffects to discovered functions by scanning around declarations (coarse)
    functions_with_tags = []
    for name in functions:
        # naive window to scan
        m = re.search(rf"\b{name}\b[\s\S]{{0,400}}", text)
        snippet = m.group(0) if m else text[:400]
        functions_with_tags.append({"name": name, "sideEffects": _side_effects(snippet)})

    return {
        "imports": imports,
        "exports": exports,
        "symbols": {"functions": functions, "classes": classes, "functionTags": functions_with_tags},
        "hints": hints,
    }
