import json
import os
import re
import sys
import subprocess
from pathlib import Path
import textwrap

# --- helpers -----------------------------------------------------------------

def _run_capabilities(repo_dir: Path) -> dict:
    """
    Runs backend/app/capabilities.py on a temp repo path and returns the parsed JSON.
    Relies only on stdout message: "Capability written to <.../capability.json>".
    """
    env = os.environ.copy()
    # Make the project importable when the script runs as a CLI
    env["PYTHONPATH"] = env.get("PYTHONPATH", os.getcwd())

    proc = subprocess.run(
        [sys.executable, "backend/app/capabilities.py", str(repo_dir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        check=True,
        cwd=Path.cwd(),
    )
    m = re.search(r"Capability written to (.+?/capability\.json)", proc.stdout)
    assert m, f"did not detect capability path in output:\n{proc.stdout}"
    cap_path = Path(m.group(1)).resolve()
    assert cap_path.exists(), f"capability.json not found at {cap_path}"
    with cap_path.open() as f:
        return json.load(f)

def _mk_fastapi_repo(dst: Path) -> None:
    """
    Minimal FastAPI repo with one GET and one POST (with Pydantic model).
    Parser should discover an entrypoint under /health.
    """
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "main.py").write_text(textwrap.dedent("""
        from fastapi import FastAPI
        from pydantic import BaseModel

        app = FastAPI()

        @app.get("/health")
        def health():
            return {"ok": True}

        class Item(BaseModel):
            name: str
            qty: int

        @app.post("/items")
        def create_item(item: Item):
            return {"received": item.dict()}
    """).strip() + "\n")

def _mk_plain_python_repo(dst: Path) -> None:
    """
    Repo with no web framework. Provis should still produce a capability
    with sane defaults (status/steps/debug) without crashing.
    """
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "util.py").write_text("def add(a, b): return a + b\n")
    (dst / "main.py").write_text(textwrap.dedent("""
        from util import add
        if __name__ == "__main__":
            print(add(2, 3))
    """).strip() + "\n")

def _paths_from(obj):
    """Collect all 'path' strings from any nested dict/list structure."""
    found = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "path" and isinstance(v, str):
                found.add(v)
            found |= _paths_from(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _paths_from(v)
    return found

# --- tests -------------------------------------------------------------------

def test_generalizes_minimal_fastapi_repo(tmp_path):
    repo = tmp_path / "fastapi_repo"
    _mk_fastapi_repo(repo)

    cap = _run_capabilities(repo)

    # Core shape
    assert isinstance(cap, dict) and cap, "capability must be a non-empty dict"
    assert cap.get("status") in {"active", "healthy"}, "status should be set"

    # Entrypoints: should include our FastAPI route(s), path ends with main.py
    eps = cap.get("entrypoints", [])
    assert isinstance(eps, list) and eps, "entrypoints must be a non-empty list"
    assert any(e.get("route") == "/health" for e in eps), "should detect /health"
    assert any(str(e.get("path", "")).endswith("main.py") for e in eps), "entrypoint path should end with main.py"

    # Control flow should not be empty for a detected web app
    cf = cap.get("control_flow", cap.get("controlFlow", []))
    assert isinstance(cf, list) and len(cf) > 0, "control_flow must be non-empty"

    # Steps: must contain canonical anchors that your builder guarantees
    titles = [s.get("title") for s in cap.get("steps", []) if isinstance(s, dict)]
    assert "Receive Request" in titles, "steps should include 'Receive Request'"
    assert "Return Success" in titles, "steps should include 'Return Success'"

    # Sanity: ensure we didn't accidentally hardcode your original repo paths
    all_paths = _paths_from(cap)
    assert not any("backend/app/routers/deck.py" in p or "backend/app/routers/email.py" in p for p in all_paths), \
        "capability should not reference project-specific router paths for an external repo"

def test_generalizes_plain_python_repo(tmp_path):
    repo = tmp_path / "plain_repo"
    _mk_plain_python_repo(repo)

    cap = _run_capabilities(repo)

    # Should not crash and should produce a structured capability
    assert isinstance(cap, dict) and cap, "capability must be a non-empty dict"
    assert cap.get("status") in {"active", "healthy"}

    # Entrypoints may be empty for non-web repos; that's OK.
    assert "entrypoints" in cap, "entrypoints key must exist (may be empty list)"
    assert isinstance(cap["entrypoints"], list)

    # Steps should still include generic anchors your builder always emits.
    titles = [s.get("title") for s in cap.get("steps", []) if isinstance(s, dict)]
    assert "Receive Request" in titles
    assert "Return Success" in titles

    # A debug block (if present) should reflect files processed > 0
    dbg = cap.get("debug", {})
    if isinstance(dbg, dict) and "files_processed" in dbg:
        assert dbg["files_processed"] >= 1
