from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.llm.client import LLMClient
from app.llm.prompts import (
    FILE_SCHEMA, CAPABILITY_SCHEMA, GLOSSARY_SCHEMA,
    file_messages, capability_messages, glossary_messages,
)
from app.utils.io import write_json_atomic

# ---------- utils ----------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _idx_files(files_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {f["path"]: f for f in files_payload.get("files", [])}

def _internal_deps(graph: Dict[str, Any], src: str) -> List[str]:
    return [e["resolved"] for e in graph.get("edges", []) if e.get("from") == src and not e.get("external") and e.get("resolved")]

def _external_deps(graph: Dict[str, Any], src: str) -> List[str]:
    return [e["to"] for e in graph.get("edges", []) if e.get("from") == src and e.get("external")]

def _entrypoints(files_payload: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for f in files_payload.get("files", []):
        h = f.get("hints", {})
        if h.get("isRoute") or h.get("isAPI"):
            out.append(f["path"])
    return out

def _one_hop_flow(graph: Dict[str, Any], entry: str) -> List[str]:
    deps = _internal_deps(graph, entry)
    return [entry] + deps

# ---------- LLM funcs ----------

async def _summ_file(llm: LLMClient, f: Dict[str, Any], graph: Dict[str, Any]) -> Dict[str, Any]:
    ctx = {
        "path": f["path"],
        "language": f.get("language"),
        "ext": f.get("ext"),
        "hints": f.get("hints", {}),
        "symbols": f.get("symbols", {}),
        "internal_dependencies": _internal_deps(graph, f["path"]),
        "external_dependencies": _external_deps(graph, f["path"]),
    }
    try:
        return await llm.acomplete_json(file_messages(ctx), FILE_SCHEMA)
    except Exception as e:
        # Minimal fallback if LLM fails (still no codegen)
        return {
            "title": f["path"].split("/")[-1],
            "purpose": None,
            "key_functions": f.get("symbols", {}).get("functions", []),
            "internal_dependencies": ctx["internal_dependencies"],
            "external_dependencies": ctx["external_dependencies"],
            "how_to_modify": None,
            "risks": None,
            "blurb": f"{f.get('language')} file.",
            "vibecoder_summary": "This file is part of the app. You can change it to adjust behavior.",
            "edit_points": [],
            "_error": str(e),
        }

async def _summ_capability(llm: LLMClient, entry: str, files_idx: Dict[str, Any], flow: List[str], hubs: List[str]) -> Dict[str, Any]:
    ctx = {
        "entrypoint": entry,
        "files": [
            {
                "path": p,
                "language": files_idx.get(p, {}).get("language"),
                "hints": files_idx.get(p, {}).get("hints"),
                "symbols": files_idx.get(p, {}).get("symbols"),
            } for p in flow
        ],
        "hubs_touched": hubs,
    }
    try:
        return await llm.acomplete_json(capability_messages(ctx), CAPABILITY_SCHEMA)
    except Exception as e:
        return {
            "title": f"Capability starting at {entry}",
            "entrypoint": entry,
            "files": flow,
            "summary": "Flow across entrypoint and its immediate internal dependencies.",
            "vibecoder_summary": "This part of the app starts here and uses a few helper files to work.",
            "edit_points": [],
            "impact": {"new_internal_edges_example": [], "hubs_touched": hubs, "risks": []},
            "_error": str(e),
        }

async def _build_glossary(llm: LLMClient, files_payload: Dict[str, Any]) -> Dict[str, Any]:
    base_terms = [
        "function", "class", "import", "export", "component", "route", "API", "schema",
        "middleware", "service", "controller", "dependency", "module", "queue", "job",
        "provider", "environment variable", "logger",
    ]
    # (Optional) Repo-specific tokens could be added later by scanning filenames.
    try:
        return await llm.acomplete_json(glossary_messages(base_terms), GLOSSARY_SCHEMA)
    except Exception as e:
        return {"terms": [{"term": "function", "dev_definition": "Reusable block of code.", "vibecoder_definition": "A recipe you can run."}], "_error": str(e)}

# ---------- public entry ----------

async def run_summarization(repo_dir: Path) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Generate file summaries, capabilities, and glossary. Persist to repo_dir."""
    files_path = repo_dir / "files.json"
    graph_path = repo_dir / "graph.json"
    files_payload = json.loads(files_path.read_text(encoding="utf-8"))
    graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))

    llm = LLMClient(cache_dir=repo_dir / "cache_llm")
    files = files_payload.get("files", [])
    idx = _idx_files(files_payload)

    # ---- file-level summaries sequentially (to avoid hanging) ----
    file_summaries = []
    for i, f in enumerate(files):
        try:
            print(f"Processing file {i+1}/{len(files)}: {f['path']}")
            summary = await _summ_file(llm, f, graph_payload)
            file_summaries.append(summary)
        except Exception as e:
            print(f"Error processing file {f['path']}: {e}")
            # Fallback: create minimal summary
            file_summaries.append({
                "title": f["path"].split("/")[-1],
                "purpose": f"A {f.get('language', 'unknown')} file.",
                "key_functions": f.get("symbols", {}).get("functions", []),
                "internal_dependencies": _internal_deps(graph_payload, f["path"]),
                "external_dependencies": _external_deps(graph_payload, f["path"]),
                "how_to_modify": "Edit this file to modify its functionality.",
                "risks": "Be careful when modifying this file.",
                "blurb": f"{f.get('language', 'unknown')} file.",
                "vibecoder_summary": "This file is part of the application.",
                "edit_points": [],
                "_error": str(e)
            })

    for f, s in zip(files, file_summaries):
        f["summary"] = s
        f["blurb"] = s.get("blurb")
        f["vibecoder_summary"] = s.get("vibecoder_summary")
        f["edit_points"] = s.get("edit_points", [])
        # Ensure stable purpose string (UI needs concise purpose)
        if not f.get("purpose"):
            f["purpose"] = s.get("purpose") or s.get("blurb") or ""

    files_payload["files"] = files
    files_payload["generatedAt"] = _now()
    write_json_atomic(files_path, files_payload)

    # ---- capabilities (seed: all entrypoints, one-hop flow) ----
    entries = _entrypoints(files_payload)
    # hubs: top degree nodes already computed in graph.metrics.topHubs if present
    hubs = graph_payload.get("metrics", {}).get("topHubs", [])[:10]
    cap_tasks = []
    for e in entries:
        flow = _one_hop_flow(graph_payload, e)
        cap_tasks.append(_summ_capability(llm, e, idx, flow, hubs))
    try:
        cap_results = await asyncio.gather(*cap_tasks, return_exceptions=True)
    except Exception as e:
        print(f"Error in capability generation: {e}")
        cap_results = []

    capabilities_payload = {
        "repoId": files_payload["repoId"],
        "generatedAt": _now(),
        "capabilities": cap_results,
    }
    write_json_atomic(repo_dir / "capabilities.json", capabilities_payload)

    # ---- glossary ----
    glossary_payload = await _build_glossary(llm, files_payload)
    glossary_payload["generatedAt"] = _now()
    # Remove internal error fields from artifact
    if "_error" in glossary_payload:
        glossary_payload.pop("_error", None)
    write_json_atomic(repo_dir / "glossary.json", glossary_payload)

    return files_payload, capabilities_payload, glossary_payload
