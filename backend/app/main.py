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
from .capabilities import (
    build_all_capabilities,
    list_capabilities_index,
    read_capability_by_id,
)
from .qa import answer_question

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

# NOTE: unified files handler with optional capability filter is defined below

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
    try:
        return list_capabilities_index(repo_dir(repo_id))
    except FileNotFoundError:
        raise HTTPException(404, detail="capabilities not found")

@app.get("/repo/{repo_id}/glossary")
def get_glossary(repo_id: str):
    require_done(repo_id)
    path = repo_dir(repo_id) / "glossary.json"
    if not path.exists():
        raise HTTPException(404, detail="glossary not found")
    return json.loads(path.read_text())

@app.post("/repo/{repo_id}/capabilities/auto")
async def post_capabilities_auto(repo_id: str):
    require_done(repo_id)
    try:
        results = await build_all_capabilities(repo_dir(repo_id))
        return {"ok": True, "capabilities": results.get("index", [])}
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to build capabilities: {e}")

@app.get("/repo/{repo_id}/capabilities/{cap_id}")
def get_capability(repo_id: str, cap_id: str):
    require_done(repo_id)
    try:
        return read_capability_by_id(repo_dir(repo_id), cap_id)
    except FileNotFoundError:
        raise HTTPException(404, detail="capability not found")

@app.get("/repo/{repo_id}/files", tags=["files"])
def get_files_filtered(repo_id: str, capability: str | None = None):
    """Optionally filter files by capability id for file cards."""
    require_done(repo_id)
    base = repo_dir(repo_id)
    files_path = base / "files.json"
    if not files_path.exists():
        raise HTTPException(404, detail="files.json not found")
    files_payload = json.loads(files_path.read_text())
    if not capability:
        return files_payload

    # Filter to files present in capability nodes
    try:
        cap = read_capability_by_id(base, capability)
    except FileNotFoundError:
        raise HTTPException(404, detail="capability not found")

    node_paths = set([n.get("path") for n in cap.get("lanes", {}).get("web", [])] +
                     [n.get("path") for n in cap.get("lanes", {}).get("api", [])] +
                     [n.get("path") for n in cap.get("lanes", {}).get("workers", [])] +
                     [n.get("path") for n in cap.get("lanes", {}).get("other", [])])

    filtered = [f for f in files_payload.get("files", []) if f.get("path") in node_paths]
    return {**files_payload, "files": filtered}

@app.post("/repo/{repo_id}/qa")
async def post_qa(repo_id: str, body: dict):
    require_done(repo_id)
    question = body.get("question")
    capability = body.get("capabilityId")
    if not question:
        raise HTTPException(400, detail="Missing 'question'")
    try:
        res = await answer_question(repo_dir(repo_id), question, capability)
        return res
    except Exception as e:
        raise HTTPException(500, detail=f"QA failed: {e}")
