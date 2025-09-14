from __future__ import annotations
import asyncio
import json
import hashlib
from pathlib import Path
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .utils.id_gen import short_id
from .status import StatusStore
from .models import (
    IngestResponse, StatusPayload,
    RepoOverviewModel, CapabilitySummaryModel, CapabilityDetailModel
)
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
    allow_origins=[settings.CORS_ORIGINS] if settings.CORS_ORIGINS else ["http://localhost:3000"],
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
    snapshot_id = short_id("snap")
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

    # Compute a deterministic hash of key settings to help with idempotency/debugging
    try:
        settings_payload = {
            "MAX_ZIP_MB": settings.MAX_ZIP_MB,
            "MAX_FILES": settings.MAX_FILES,
            "MAX_FILE_MB": settings.MAX_FILE_MB,
            "IGNORED_DIRS": list(settings.IGNORED_DIRS),
            "IGNORED_EXTS": list(settings.IGNORED_EXTS),
        }
        settings_hash = hashlib.sha256(json.dumps(settings_payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    except Exception:
        settings_hash = "default"

    return IngestResponse(repoId=repo_id, jobId=job_id, snapshotId=snapshot_id, settingsHash=settings_hash)

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

# ------------------------- V1 API -------------------------
@app.get("/v1/repo/{repo_id}", tags=["v1"], response_model=RepoOverviewModel)
def get_repo_overview(repo_id: str):
    require_done(repo_id)
    base = repo_dir(repo_id)
    t = base / "tree.json"
    f = base / "files.json"
    c = base / "capabilities.json"
    m = base / "metrics.json"
    if not (t.exists() and f.exists() and c.exists() and m.exists()):
        raise HTTPException(404, detail="one or more artifacts missing")
    caps = json.loads(c.read_text()).get("capabilities")
    return {
        "tree": json.loads(t.read_text()),
        "files": json.loads(f.read_text()),
        "capabilities": [
            {
                **c,
                "entryPoints": c.get("entryPoints") or [e.get("path") if isinstance(e, dict) else e for e in c.get("entrypoints", [])],
            }
            for c in (caps or [])
        ],
        "metrics": json.loads(m.read_text()),
    }

@app.get("/v1/repo/{repo_id}/capabilities", tags=["v1"], response_model=list[CapabilitySummaryModel])
def list_caps_v1(repo_id: str):
    require_done(repo_id)
    base = repo_dir(repo_id)
    # Use the capabilities index which has the summary format
    index_path = base / "capabilities" / "index.json"
    if not index_path.exists():
        raise HTTPException(404, detail="capabilities index not found")
    
    index_data = json.loads(index_path.read_text())
    caps = index_data.get("index", [])
    
    # Ensure all required fields have defaults
    for cap in caps:
        cap.setdefault("purpose", "")
        cap.setdefault("entryPoints", [e.get("path") if isinstance(e, dict) else e for e in cap.get("anchors", [])])
        cap.setdefault("keyFiles", [])
        cap.setdefault("dataIn", [])
        cap.setdefault("dataOut", [])
        cap.setdefault("sources", [])
        cap.setdefault("sinks", [])
    
    return caps

@app.get("/v1/repo/{repo_id}/file", tags=["v1"])
def get_file_details(repo_id: str, path: str):
    require_done(repo_id)
    base = repo_dir(repo_id)
    f = base / "files.json"
    if not f.exists():
        raise HTTPException(404, detail="files.json not found")
    data = json.loads(f.read_text())
    
    for entry in data.get("files", []):
        if entry.get("path") == path:
            result = {
                "path": path,
                "purpose": entry.get("purpose") or entry.get("blurb") or "",
                "exports": entry.get("exports", []),
                "imports": [i.get("resolved") or i.get("raw") for i in entry.get("imports", [])],
                "functions": entry.get("symbols", {}).get("functions", []),
                "loc": entry.get("loc", 0),
                "lang": entry.get("lang", ""),
            }
            
            # Always try to load from cache first to get rich LLM summaries
            cache_match = None
            try:
                cache_dir = base / "cache_llm"
                if cache_dir.exists():
                    filename = entry["path"].split("/")[-1]
                    file_base = filename.split(".")[0]
                    file_type = entry.get("language", "")
                    
                    # Look through ALL cache files for file summaries
                    best_match = None
                    best_score = 0
                    
                    for cache_file in cache_dir.glob("*.json"):
                        try:
                            llm_data = json.loads(cache_file.read_text())
                            
                            # Skip if this doesn't look like a file summary
                            if not llm_data.get("title") or not llm_data.get("purpose"):
                                continue
                                
                            # Skip QA responses and glossaries
                            if "answer" in llm_data or "glossary" in llm_data:
                                continue
                            
                            title = llm_data.get("title", "").lower()
                            purpose = llm_data.get("purpose", "").lower()
                            dev_summary = llm_data.get("dev_summary", "").lower()
                            blurb = llm_data.get("blurb", "").lower()
                            
                            score = 0
                            
                            # Exact filename match in title
                            if filename.lower() in title:
                                score += 20
                                
                            # Base filename match in title
                            if file_base.lower() in title:
                                score += 15
                                
                            # Exact filename match anywhere
                            if filename.lower() in (purpose + dev_summary + blurb):
                                score += 10
                                
                            # File type keywords matching
                            if "router" in entry["path"].lower():
                                if any(word in (title + purpose) for word in ["router", "route", "endpoint", "api"]):
                                    score += 15
                            elif "model" in entry["path"].lower():
                                if any(word in (title + purpose) for word in ["model", "database", "schema", "data"]):
                                    score += 15
                            elif "service" in entry["path"].lower():
                                if any(word in (title + purpose) for word in ["service", "business", "logic"]):
                                    score += 15
                            elif "main" in entry["path"].lower():
                                if any(word in (title + purpose) for word in ["main", "entry", "application", "app"]):
                                    score += 15
                                    
                            # Technology match
                            if file_type == "py" and any(tech in purpose for tech in ["fastapi", "python", "django"]):
                                score += 8
                            elif file_type in ["ts", "js"] and any(tech in purpose for tech in ["next", "react", "typescript", "javascript"]):
                                score += 8
                                
                            # Quality content bonus
                            if len(purpose) > 100 and "configures" in purpose:
                                score += 5
                            if len(dev_summary) > 50:
                                score += 5
                            if len(blurb) > 50 and ("think of" in blurb or "imagine" in blurb):
                                score += 5
                                
                            if score > best_score and score >= 5:  # Lower threshold
                                best_score = score
                                best_match = llm_data
                                
                        except Exception:
                            continue
                    
                    # Use the best match if found
                    if best_match:
                        cache_match = best_match
                        
            except Exception:
                pass
            
            # Apply cache data if found, otherwise use embedded summary
            if cache_match:
                result.update({
                    "summary": cache_match.get("dev_summary") or cache_match.get("purpose") or result["purpose"],
                    "title": cache_match.get("title", result.get("title", "")),
                    "key_functions": cache_match.get("key_functions", []),
                    "how_to_modify": cache_match.get("how_to_modify", ""),
                    "risks": cache_match.get("risks", ""),
                    "blurb": cache_match.get("blurb", result.get("blurb", "")),
                    "vibecoder_summary": cache_match.get("vibecoder_summary", ""),
                    "edit_points": cache_match.get("edit_points", ""),
                    "dev_summary": cache_match.get("dev_summary", ""),
                    "external_dependencies": cache_match.get("external_dependencies", []),
                    "internal_dependencies": cache_match.get("internal_dependencies", []),
                })
            else:
                # Fallback to embedded summary if available
                summary_data = entry.get("summary", {})
                if summary_data:
                    result.update({
                        "summary": summary_data.get("dev_summary") or summary_data.get("blurb") or summary_data.get("purpose") or result["purpose"],
                        "title": summary_data.get("title", ""),
                        "key_functions": summary_data.get("key_functions", []),
                        "how_to_modify": summary_data.get("how_to_modify", ""),
                        "risks": summary_data.get("risks", ""),
                        "blurb": summary_data.get("blurb", entry.get("blurb", "")),
                        "vibecoder_summary": summary_data.get("vibecoder_summary", ""),
                        "edit_points": summary_data.get("edit_points", ""),
                        "external_dependencies": summary_data.get("external_dependencies", []),
                        "internal_dependencies": summary_data.get("internal_dependencies", []),
                        "dev_summary": summary_data.get("dev_summary", ""),
                    })
            
            return result
    
    raise HTTPException(404, detail="file not found")

@app.get("/v1/repo/{repo_id}/capabilities/{cap_id}", tags=["v1"], response_model=CapabilityDetailModel)
def get_cap_v1(repo_id: str, cap_id: str):
    require_done(repo_id)
    base = repo_dir(repo_id)
    try:
        cap = read_capability_by_id(base, cap_id)
    except FileNotFoundError:
        raise HTTPException(404, detail="capability not found")
    # Ensure camelCase mirrors
    if "control_flow" in cap and "controlFlow" not in cap:
        cap["controlFlow"] = cap.get("control_flow")
    if "data_flow" in cap and "dataFlow" not in cap:
        cap["dataFlow"] = cap.get("data_flow")
    if "entryPoints" not in cap and "entrypoints" in cap:
        cap["entryPoints"] = [e.get("path") if isinstance(e, dict) else e for e in cap.get("entrypoints", [])]
    # Ensure swimlanes present and complete
    swim = cap.get("swimlanes") or {}
    for k in ("web","api","workers","other"):
        swim.setdefault(k, [])
    cap["swimlanes"] = swim
    # Ensure nodeIndex exists (fallback build)
    if "nodeIndex" not in cap:
        node_index = {}
        entry_set = set(cap.get("entryPoints", []))
        in_map = {}
        out_map = {}
        for e in cap.get("controlFlow", []):
            out_map.setdefault(e["from"], []).append(e["to"])
            in_map.setdefault(e["to"], []).append(e["from"])
        all_nodes = set()
        for arr in swim.values():
            for it in arr:
                all_nodes.add(it if isinstance(it, str) else it.get("path"))
        lane_for = {}
        for lane, arr in swim.items():
            for it in arr:
                p = it if isinstance(it, str) else it.get("path")
                lane_for[p] = lane
        for n in all_nodes:
            incoming = in_map.get(n, [])
            outgoing = out_map.get(n, [])
            role = "entrypoint" if n in entry_set else ("sink" if len(outgoing) == 0 else "handler")
            node_index[n] = {"lane": lane_for.get(n, "other"), "role": role, "incoming": incoming, "outgoing": outgoing}
        cap["nodeIndex"] = node_index
    # Guarantee presence of optional arrays/objects
    cap.setdefault("steps", [])
    cap.setdefault("nodeIndex", {})
    cap.setdefault("policies", [])
    cap.setdefault("contracts", [])
    cap.setdefault("suspectRank", [])
    cap.setdefault("recentChanges", [])
    return cap

@app.get("/repo/{repo_id}/tree")
def get_tree(repo_id: str):
    require_done(repo_id)
    path = repo_dir(repo_id) / "tree.json"
    if not path.exists():
        raise HTTPException(404, detail="tree.json not found")
    return json.loads(path.read_text())

@app.get("/repo/{repo_id}/metrics")
def get_metrics(repo_id: str):
    require_done(repo_id)
    path = repo_dir(repo_id) / "metrics.json"
    if not path.exists():
        raise HTTPException(404, detail="metrics not found")
    return json.loads(path.read_text())

@app.get("/repo/{repo_id}/suggestions")
def get_suggestions(repo_id: str, capability: str = None):
    """Get edit suggestions for a capability or the entire repo."""
    require_done(repo_id)
    
    # Load files and capabilities data
    files_path = repo_dir(repo_id) / "files.json"
    caps_path = repo_dir(repo_id) / "capabilities.json"
    
    if not files_path.exists():
        raise HTTPException(404, detail="files.json not found")
    if not caps_path.exists():
        raise HTTPException(404, detail="capabilities.json not found")
    
    files_data = json.loads(files_path.read_text())
    caps_data = json.loads(caps_path.read_text())
    
    # Find target capability if specified
    target_cap = None
    if capability:
        for cap in caps_data.get("capabilities", []):
            if cap.get("id") == capability:
                target_cap = cap
                break
        if not target_cap:
            raise HTTPException(404, detail=f"Capability {capability} not found")
    
    # Generate suggestions based on file analysis
    suggestions = []
    files = files_data.get("files", [])
    
    for f in files:
        if target_cap:
            # Only suggest files in the target capability
            cap_files = set()
            for lane_files in target_cap.get("swimlanes", {}).values():
                if isinstance(lane_files, list):
                    for it in lane_files:
                        cap_files.add(it if isinstance(it, str) else it.get("path"))
            if f["path"] not in cap_files:
                continue
        
        # Analyze file for suggestion potential
        confidence = "Low"
        rationale = "General file for potential edits"
        
        # Check for high-impact indicators
        symbols = f.get("symbols", {})
        functions = symbols.get("functions", [])
        classes = symbols.get("classes", [])
        
        if functions and classes:
            confidence = "High"
            rationale = f"Contains {len(functions)} functions and {len(classes)} classes - high edit potential"
        elif functions:
            confidence = "Med"
            rationale = f"Contains {len(functions)} functions - moderate edit potential"
        elif classes:
            confidence = "Med"
            rationale = f"Contains {len(classes)} classes - moderate edit potential"
        
        # Check for framework hints
        hints = f.get("hints", {})
        if hints.get("isRoute") or hints.get("isAPI"):
            confidence = "High"
            rationale = "Route/API file - critical for functionality"
        elif hints.get("isReactComponent"):
            confidence = "Med"
            rationale = "React component - UI modification target"
        
        # Extra heuristics for v1 flavor
        p = f.get("path", "").lower()
        if "/styles/" in p or p.endswith(".css"):
            confidence = "Med"
            rationale = "print/layout might clip slides"
        if "templates" in p:
            confidence = "High"
            rationale = "renderer entry point"
        if "compile" in p:
            confidence = "High"
            rationale = "orchestrator"

        # Check for warnings (potential issues)
        warnings = f.get("warnings", [])
        if warnings:
            confidence = "High"
            rationale = f"Has {len(warnings)} warnings - likely needs attention"
        
        suggestions.append({
            "fileId": f["path"],
            "rationale": rationale,
            "confidence": confidence
        })
    
    # Sort by confidence (High, Med, Low)
    confidence_order = {"High": 0, "Med": 1, "Low": 2}
    suggestions.sort(key=lambda x: confidence_order.get(x["confidence"], 3))
    
    return {
        "repoId": repo_id,
        "capability": capability,
        "suggestions": suggestions[:20],  # Limit to top 20
        "generatedAt": datetime.now(timezone.utc).isoformat()
    }

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

    # Prefer swimlanes; tolerate both string paths and {path} objects
    import itertools as _it
    swim = cap.get("swimlanes", {}) or {}
    seqs = list(swim.values())
    flat: List[str] = []
    for seq in seqs:
        for it in (seq or []):
            flat.append(it if isinstance(it, str) else it.get("path"))
    node_paths = set([p for p in flat if p])
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
