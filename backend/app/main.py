import asyncio
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
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
    return settings.DATA_DIR / repo_id

def require_done(repo_id: str):
    """Helper to ensure repository processing is complete before allowing access."""
    s = StatusStore(repo_dir(repo_id)).read()
    if s.phase != "done":
        raise HTTPException(409, detail={"status": s.model_dump()})

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/ingest", response_model=IngestResponse)
async def ingest_repo(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, detail="Only .zip uploads supported in Step 1")

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

    await job_queue.enqueue(job_id, rdir)
    return IngestResponse(repoId=repo_id, jobId=job_id)

@app.get("/status/{job_id}", response_model=StatusPayload)
async def get_status(job_id: str):
    for p in settings.DATA_DIR.glob("repo_*/status.json"):
        store = StatusStore(p.parent)
        s = store.read()
        if s.jobId == job_id:
            return s
    raise HTTPException(404, detail="Job not found")
