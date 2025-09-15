import tempfile
from pathlib import Path

from app.import_resolver import ImportResolver


def write(p: Path, text: str = ""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_python_trie_resolution_poetry_like_repo(tmp_path: Path):
    # Mock Poetry-like layout
    repo = tmp_path
    write(repo / "pyproject.toml", """
[tool.poetry]
name = "acme"
version = "0.1.0"
""")
    write(repo / "acme/__init__.py", "")
    write(repo / "acme/utils/__init__.py", "")
    write(repo / "acme/utils/math.py", "def add(a,b): return a+b\n")

    resolver = ImportResolver(repo, tsconfig_paths={}, pyproject_packages=["acme"])
    from_file = repo / "acme/app/main.py"
    write(from_file, "from acme.utils import math\n")

    # Simulate ImportModel
    from app.models import ImportModel
    model = ImportModel(raw="acme.utils.math", resolved=None, external=True, kind="py", confidence=0.0, hypothesis=False, reason_code=None, evidence=[])
    out = resolver.resolve_import(model, from_file)

    assert out.resolved is not None
    assert out.external is False
    assert out.confidence >= 0.7


def test_ts_trie_resolution_node_modules(tmp_path: Path):
    repo = tmp_path
    # Create node_modules with package
    pkg_dir = repo / "node_modules/lodash"
    write(pkg_dir / "index.js", "module.exports = {}\n")
    # Create a source file
    src = repo / "src/index.ts"
    write(src, "import _ from 'lodash'\n")

    resolver = ImportResolver(repo, tsconfig_paths={}, pyproject_packages=[])
    from app.models import ImportModel
    model = ImportModel(raw="lodash", resolved=None, external=True, kind="esm", confidence=0.0, hypothesis=False, reason_code=None, evidence=[])
    out = resolver.resolve_import(model, src)

    assert out.resolved is not None
    assert out.external is False
    assert out.confidence >= 0.65


