from __future__ import annotations
import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .utils.id_gen import short_id
from .status import StatusStore
from .models import IngestResponse, StatusPayload
from .ingest import stage_upload, extract_snapshot
from .jobs import job_queue

app = FastAPI(title="Provis Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def _startup():
    asyncio.create_task(job_queue.start_worker())

def repo_dir(repo_id: str) -> Path:
    return Path(settings.DATA_DIR) / repo_id

@app.get("/health")
def health():
    return {"ok": True}

def require_done(repo_id: str):
    store = StatusStore(repo_dir(repo_id))
    s = store.read()
    if s.phase != "done":
        raise HTTPException(status_code=409, detail={"status": s.model_dump()})

@app.post("/ingest", response_model=IngestResponse)
async def ingest_repo(file: UploadFile = File(...), bg: BackgroundTasks = None):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, detail="Only .zip uploads supported")

    repo_id = short_id("repo")
    job_id = short_id("job")
    rdir = repo_dir(repo_id)
    snapshot = rdir / "snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)

    store = StatusStore(rdir)
    store.update(jobId=job_id, repoId=repo_id, phase="queued", pct=0, filesParsed=0, imports=0, warnings=[])

    tmp_zip = await stage_upload(rdir, file)
    try:
        count = extract_snapshot(tmp_zip, snapshot)
        store.update(filesParsed=count)
    except Exception as e:
        store.update(phase="failed", pct=100, error=str(e))
        raise HTTPException(400, detail=f"Extraction failed: {e}")
    finally:
        try:
            tmp_zip.unlink(missing_ok=True)
        except Exception:
            pass

    # Run as background task to avoid dev queue/reload pitfalls
    if bg is not None:
        bg.add_task(job_queue._run_job, job_id, rdir)
    else:
        asyncio.create_task(job_queue._run_job(job_id, rdir))

    return IngestResponse(repoId=repo_id, jobId=job_id)

@app.get("/status/{job_id}", response_model=StatusPayload)
async def get_status(job_id: str):
    for p in Path(settings.DATA_DIR).glob("repo_*/status.json"):
        store = StatusStore(p.parent)
        s = store.read()
        if s.jobId == job_id:
            return s
    raise HTTPException(404, detail="Job not found")

@app.get("/repo/{repo_id}/files")
def get_files(repo_id: str):
    require_done(repo_id)
    path = repo_dir(repo_id) / "files.json"
    if not path.exists():
        raise HTTPException(404, detail="files.json not found")
    return json.loads(path.read_text())

@app.get("/repo/{repo_id}/graph")
def get_graph(repo_id: str):
    require_done(repo_id)
    path = repo_dir(repo_id) / "graph.json"
    if not path.exists():
        raise HTTPException(404, detail="graph.json not found")
    return json.loads(path.read_text())

@app.get("/repo/{repo_id}/capabilities")
def get_capabilities(repo_id: str):
    require_done(repo_id)
    path = repo_dir(repo_id) / "capabilities.json"
    if not path.exists():
        raise HTTPException(404, detail="capabilities not found")
    return json.loads(path.read_text())

@app.get("/repo/{repo_id}/glossary")
def get_glossary(repo_id: str):
    require_done(repo_id)
    path = repo_dir(repo_id) / "glossary.json"
    if not path.exists():
        raise HTTPException(404, detail="glossary not found")
    return json.loads(path.read_text())
