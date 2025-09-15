from __future__ import annotations
import asyncio
import json
import hashlib
from datetime import datetime
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
    cap_dir = base / "capabilities"
    index_path = cap_dir / "index.json"
    if not index_path.exists():
        raise HTTPException(404, detail="capabilities index not found")

    index_data = json.loads(index_path.read_text())
    cap_ids = index_data.get("index", [])

    caps = []
    for cap_id in cap_ids:
        # Handle both string IDs and dict objects (legacy compatibility)
        if isinstance(cap_id, dict):
            cap_id = cap_id.get("id", "unknown")
        elif not isinstance(cap_id, str):
            continue  # Skip invalid entries
            
        cap_file = cap_dir / cap_id / "capability.json"
        if cap_file.exists():
            try:
                cap_data = json.loads(cap_file.read_text())
                cap_data.setdefault("purpose", "")
                cap_data.setdefault("entryPoints", [e.get("path") if isinstance(e, dict) else e for e in cap_data.get("entrypoints", [])])
                cap_data.setdefault("keyFiles", [])
                cap_data.setdefault("dataIn", [])
                cap_data.setdefault("dataOut", [])
                cap_data.setdefault("sources", [])
                cap_data.setdefault("sinks", [])
                caps.append(cap_data)
            except Exception as e:
                print(f"Warning: Could not load capability {cap_id}: {e}")
                continue

    return caps

@app.post("/v1/repo/{repo_id}/capabilities/rebuild", tags=["v1"])
async def rebuild_caps_v1(repo_id: str):
    base = repo_dir(repo_id)
    from .capabilities import build_all_capabilities
    caps = await build_all_capabilities(base)
    cap_dir = base / "capabilities"
    # build_all_capabilities now returns a list of capability IDs
    idx = {"index": caps if isinstance(caps, list) else []}
    (cap_dir / "index.json").write_text(json.dumps(idx, indent=2))
    return {"ok": True, "count": len(idx["index"])}

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
            
            # Try to find cache file by looking for file-specific summaries
            cache_match = None
            try:
                cache_dir = base / "cache_llm"
                if cache_dir.exists():
                    filename = entry["path"].split("/")[-1]
                    file_base = filename.split(".")[0]
                    
                    # Look through cache files for ones that match this specific file
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
                            
                            score = 0
                            
                            # Exact filename match in title (highest priority)
                            if filename.lower() in title:
                                score += 100
                                
                            # Base filename match in title
                            if file_base.lower() in title:
                                score += 80
                                
                            # Exact filename match anywhere in content
                            if filename.lower() in (purpose + dev_summary):
                                score += 60
                                
                            # Path-based matching for domain-locker files
                            file_path = entry["path"].lower()
                            if "domains" in file_path:
                                if any(word in (title + purpose) for word in ["domain", "domains", "registration", "search", "add"]):
                                    score += 40
                                # Strong penalty for non-domain related summaries
                                elif any(word in (title + purpose) for word in ["demo", "component", "navigation", "icon", "svg"]):
                                    score -= 50
                            elif "monitor" in file_path:
                                if any(word in (title + purpose) for word in ["monitor", "monitoring", "status", "health", "uptime"]):
                                    score += 40
                            elif "utils" in file_path:
                                if any(word in (title + purpose) for word in ["utility", "util", "helper", "tool", "pg-api"]):
                                    score += 40
                            elif "services" in file_path:
                                if any(word in (title + purpose) for word in ["service", "business", "logic", "api", "database"]):
                                    score += 40
                            elif "components" in file_path:
                                if any(word in (title + purpose) for word in ["component", "ui", "interface", "display"]):
                                    score += 40
                                
                            # Only use matches with high confidence
                            if score > best_score and score >= 80:
                                best_score = score
                                best_match = llm_data
                                
                        except Exception:
                            continue
                    
                    # Use the best match if found
                    if best_match:
                        cache_match = best_match
                            
            except Exception as e:
                # If cache matching fails, fall back to no cache match
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
        return {"ok": True, "capabilities": results if isinstance(results, list) else []}
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

@app.post("/v1/repo/{repo_id}/capabilities/{cap_id}/scenarios")
async def generate_scenario_analysis(repo_id: str, cap_id: str, scenario: str = "happy"):
    """Generate LLM-powered scenario analysis for a capability"""
    try:
        # Load capability data
        base = Path(f"data/{repo_id}")
        cap_file = base / "capabilities" / cap_id / "capability.json"
        
        if not cap_file.exists():
            raise HTTPException(404, detail=f"Capability {cap_id} not found")
        
        capability_data = json.loads(cap_file.read_text())
        
        # Prepare context for LLM
        # Normalize lists that may contain strings or {path} objects
        def _norm_list(items):
            out = []
            for it in (items or []):
                if isinstance(it, str):
                    out.append(it)
                elif isinstance(it, dict):
                    p = it.get("path") or it.get("file") or it.get("name")
                    if isinstance(p, str):
                        out.append(p)
            return out

        entry_points = _norm_list(capability_data.get("entryPoints"))
        sources = _norm_list(capability_data.get("sources"))
        sinks = _norm_list(capability_data.get("sinks"))
        data_in = _norm_list(capability_data.get("dataIn"))
        data_out = _norm_list(capability_data.get("dataOut"))
        steps = capability_data.get("steps", [])
        control_flow = capability_data.get("controlFlow") or capability_data.get("control_flow") or []
        swimlanes = capability_data.get("swimlanes", {})

        # Build an allowlist of file paths relevant to this capability
        allowed_files_set = set()
        for lane_nodes in (swimlanes or {}).values():
            for it in (lane_nodes or []):
                allowed_files_set.add(it if isinstance(it, str) else (it.get("path") or ""))
        for e in (control_flow or []):
            if isinstance(e, dict):
                if e.get("from"):
                    allowed_files_set.add(e.get("from"))
                if e.get("to"):
                    allowed_files_set.add(e.get("to"))
        for st in (steps or []):
            fid = st.get("fileId")
            if isinstance(fid, str):
                allowed_files_set.add(fid)
        # Remove empties
        allowed_files = sorted([p for p in allowed_files_set if p])
        
        # Build context for scenario analysis
        context = f"""
Capability: {capability_data.get("name", cap_id)}
Purpose: {capability_data.get("purpose", "No description available")}

Entry Points: {', '.join(entry_points)}
Data Sources: {', '.join(sources)}
Data Sinks: {', '.join(sinks)}
Input Data: {', '.join(data_in)}
Output Data: {', '.join(data_out)}

Steps:
"""
        for i, step in enumerate(steps, 1):
            context += f"{i}. {step.get('title', 'Unknown step')}: {step.get('description', 'No description')}\n"
            if step.get('fileId'):
                context += f"   File: {step['fileId']}\n"

        # Add compact control flow and lanes
        context += "\nControl Flow (from -> to):\n"
        for e in control_flow:
            try:
                context += f"- {e.get('from')} -> {e.get('to')} ({e.get('kind','call')})\n"
            except Exception:
                continue

        context += "\nSwimlanes:\n"
        for lane, nodes in (swimlanes or {}).items():
            context += f"- {lane}: {', '.join([n if isinstance(n, str) else n.get('path','') for n in (nodes or [])])}\n"

        context += "\nAllowed Files (strict):\n" + "\n".join([f"- {p}" for p in allowed_files]) + "\n"
        
        # Generate scenario-specific analysis
        messages = [
            {
                "role": "system",
                "content": """You are an expert software architect analyzing application flows. Respond STRICTLY as minified JSON matching the provided schema. Do not include commentary or markdown. Generate a detailed scenario analysis that includes:

1. **Happy Path**: The ideal execution flow with all components working correctly
2. **Edge Cases**: Common failure scenarios and how the system handles them
3. **Error Handling**: What happens when things go wrong
4. **Dependencies**: External systems and potential points of failure

Be specific about the actual files and components involved. Use the exact file paths and component names provided in the context. Only reference files present in the 'Allowed Files (strict)' list. Do NOT talk about generic app initialization, middleware setup, or unrelated routes. Focus only on this capability's end-to-end flow. Output schema:
{
  "happy_path": string[],
  "edge_cases": string[],
  "analysis"?: string
}
"""
            },
            {
                "role": "user", 
                "content": f"""Analyze this capability for the "{scenario}" scenario:

{context}

Please provide:
1. **Happy Path Flow**: Step-by-step execution when everything works
2. **Edge Cases**: 3-4 specific failure scenarios with how they're handled
3. **Error Recovery**: What happens when components fail
4. **Dependencies**: Critical external dependencies that could cause issues

Focus on realistic scenarios based on the actual codebase structure."""
            }
        ]
        
        # Use the LLM client to generate structured analysis
        from app.llm.client import LLMClient
        llm = LLMClient(cache_dir=base / "cache_llm")

        schema = {
            "type": "object",
            "properties": {
                "happy_path": {"type": "array", "items": {"type": "string"}},
                "edge_cases": {"type": "array", "items": {"type": "string"}},
                "analysis": {"type": "string"}
            },
            "required": ["happy_path", "edge_cases"],
            "additionalProperties": True
        }

        payload = await llm.acomplete_json(messages=messages, schema=schema)
        # Prefer structured result
        happy_path = payload.get("happy_path") or []
        edge_cases = payload.get("edge_cases") or []
        analysis = payload.get("analysis") or ""

        # If analysis is not a string, serialize minimally
        if not isinstance(analysis, str):
            try:
                analysis = json.dumps(analysis)
            except Exception:
                analysis = ""
        
        # Prefer structured result if present
        if isinstance(payload, dict):
            hp = payload.get("happy_path")
            ec = payload.get("edge_cases")
            if isinstance(hp, list) and isinstance(ec, list) and hp and ec:
                happy_path = hp
                edge_cases = ec

        # Post-filter out generic/unrelated items and enforce allowed files
        def _is_generic(line: str) -> bool:
            l = (line or "").lower()
            generic_terms = [
                "initialize application", "start the fastapi", "setup middleware",
                "register routes", "mount api routers", "prospects, decks, and emails",
            ]
            return any(g in l for g in generic_terms)

        def _mentions_allowed(line: str) -> bool:
            if not allowed_files:
                return True
            for p in allowed_files:
                if p and p in (line or ""):
                    return True
            return False

        happy_path = [s for s in happy_path if not _is_generic(s) and _mentions_allowed(s)]
        edge_cases = [s for s in edge_cases if not _is_generic(s)]

        # If too sparse, synthesize from steps
        if len(happy_path) < 3 and steps:
            synth = []
            for st in steps:
                title = st.get("title") or "Step"
                desc = st.get("description") or ""
                fid = st.get("fileId") or ""
                piece = title
                if desc:
                    piece += f": {desc}"
                if fid:
                    piece += f" (file: {fid})"
                synth.append(piece)
            if synth:
                happy_path = synth[:6]

        # If still empty, provide a minimal fallback
        if not happy_path and not edge_cases:
            # Attempt to parse any lines from analysis for robustness
            if isinstance(analysis, str) and analysis:
                for raw in analysis.split('\n'):
                    line = raw.strip()
                    if not line:
                        continue
                    if any(k in line.lower() for k in ["happy", "ideal path"]):
                        happy_path.append(line)
                    elif any(k in line.lower() for k in ["edge", "failure", "error"]):
                        edge_cases.append(line)
            if not happy_path and not edge_cases:
                happy_path = ["Flow generated, but details unavailable."]
                edge_cases = ["Edge cases not extracted."]
        
        return {
            "scenario": scenario,
            "capability_id": cap_id,
            "analysis": analysis,
            "happy_path": happy_path,
            "edge_cases": edge_cases,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(500, detail=f"Scenario analysis failed: {e}")
