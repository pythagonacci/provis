from __future__ import annotations
from pathlib import Path
import json
import os
import tempfile
from typing import Any
from dataclasses import is_dataclass, asdict
from datetime import datetime, date
from enum import Enum


def _safe_default(o: Any):
    """Best-effort JSON serializer for Pydantic models, dataclasses, Paths, Enums, sets, and datetimes."""
    try:
        # Pydantic v2 BaseModel
        if hasattr(o, "model_dump") and callable(getattr(o, "model_dump")):
            return o.model_dump()
    except Exception:
        pass

    # Dataclasses
    if is_dataclass(o):
        try:
            return asdict(o)
        except Exception:
            pass

    # Common problematic types
    if isinstance(o, (Path,)):
        return str(o)
    if isinstance(o, (set, frozenset)):
        return list(o)
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Enum):
        return o.value if hasattr(o, "value") else str(o)

    # Fallback: try stringifying
    return str(o)

def write_json_atomic(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, indent=2, ensure_ascii=False, default=_safe_default)
    dirpath = str(path.parent)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=dirpath, prefix=".tmp_", suffix=".json") as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)
