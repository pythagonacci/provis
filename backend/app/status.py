from __future__ import annotations
from pathlib import Path
from .models import StatusPayload
import json

class StatusStore:
    def __init__(self, repo_dir: Path):
        self.repo_dir = repo_dir
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        self.status_file = self.repo_dir / "status.json"
        if not self.status_file.exists():
            self.write(StatusPayload(
                jobId="", repoId=self.repo_dir.name,
                phase="queued", pct=0,
                filesParsed=0, imports=0, 
                importsTotal=0, importsInternal=0, importsExternal=0,
                filesSummarized=0, capabilitiesBuilt=0,
                warnings=[]
            ))

    def write(self, payload: StatusPayload) -> None:
        with self.status_file.open("w", encoding="utf-8") as f:
            json.dump(payload.model_dump(), f, indent=2)

    def read(self) -> StatusPayload:
        with self.status_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Handle backward compatibility for existing status files
        if "importsTotal" not in data:
            data["importsTotal"] = data.get("imports", 0)
        if "importsInternal" not in data:
            data["importsInternal"] = 0
        if "importsExternal" not in data:
            data["importsExternal"] = data.get("imports", 0)
        if "filesSummarized" not in data:
            data["filesSummarized"] = 0
        if "capabilitiesBuilt" not in data:
            data["capabilitiesBuilt"] = 0
            
        return StatusPayload(**data)

    def update(self, **kwargs) -> StatusPayload:
        cur = self.read()
        new = cur.model_copy(update=kwargs)
        self.write(new)
        return new
