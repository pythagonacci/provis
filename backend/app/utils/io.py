from __future__ import annotations
from pathlib import Path
import json
import os
import tempfile
from typing import Any

def write_json_atomic(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, indent=2)
    dirpath = str(path.parent)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=dirpath, prefix=".tmp_", suffix=".json") as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)
