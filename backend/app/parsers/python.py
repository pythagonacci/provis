from __future__ import annotations
from pathlib import Path
import ast
from typing import Dict, Any, List

def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return p.read_text(encoding="latin-1", errors="ignore")

def parse_python_file(p: Path) -> Dict[str, Any]:
    text = _read_text(p)
    tree = ast.parse(text)

    imports: List[Dict[str, Any]] = []
    functions: List[str] = []
    classes: List[str] = []
    hints = {"framework": None, "isRoute": False, "isReactComponent": False, "isAPI": False}

    for node in tree.body:
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.append({"raw": n.name, "kind": "py"})
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imports.append({"raw": mod, "kind": "py"})
        elif isinstance(node, ast.FunctionDef):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)

    # Very rough FastAPI detection
    if "fastapi" in (i["raw"] for i in imports):
        hints["framework"] = "fastapi"
        # If there are decorator calls like @app.get("/path")
        if any(isinstance(node, ast.FunctionDef) and node.decorator_list for node in tree.body):
            hints["isAPI"] = True
            hints["isRoute"] = True

    return {
        "imports": imports,
        "exports": [],  # Python doesn't use export; leave empty
        "symbols": {"functions": functions, "classes": classes},
        "hints": hints,
    }
