from __future__ import annotations
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.llm.client import LLMClient
from app.llm.prompts import (
    FILE_SCHEMA, CAPABILITY_SCHEMA, GLOSSARY_SCHEMA,
    file_messages, capability_messages, glossary_messages,
)
from app.utils.io import write_json_atomic
from app.config import settings
from app.observability import get_metrics_collector

logger = logging.getLogger(__name__)

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

def _generate_file_blurb(file_data: Dict[str, Any]) -> str:
    """Generate a short blurb for a file if LLM summary is not available."""
    language = file_data.get("language", "unknown")
    path = file_data.get("path", "")
    filename = path.split("/")[-1] if path else "file"
    
    # Try to infer purpose from hints
    hints = file_data.get("hints", {})
    if hints.get("isRoute"):
        return f"Route handler for {filename}"
    elif hints.get("isAPI"):
        return f"API endpoint in {filename}"
    elif hints.get("isComponent"):
        return f"React component {filename}"
    elif hints.get("isService"):
        return f"Service module {filename}"
    elif filename.endswith(".test.") or filename.endswith(".spec."):
        return f"Test file for {filename}"
    else:
        return f"{language} file {filename}"

async def _summ_file(llm: LLMClient, f: Dict[str, Any], graph: Dict[str, Any]) -> Dict[str, Any]:
    """Generate LLM summary for a single file with proper error handling."""
    metrics = get_metrics_collector()
    
    # Build compact context (keep ≤1-2k tokens)
    symbols = f.get("symbols", {})
    # Trim large arrays to keep context manageable
    trimmed_symbols = {
        "functions": symbols.get("functions", [])[:10],  # Limit to first 10 functions
        "classes": symbols.get("classes", [])[:5],       # Limit to first 5 classes
        "constants": symbols.get("constants", [])[:5],   # Limit to first 5 constants
        "hooks": symbols.get("hooks", [])[:5],           # Limit to first 5 hooks
        "components": symbols.get("components", [])[:5], # Limit to first 5 components
    }
    
    ctx = {
        "path": f["path"],
        "language": f.get("language"),
        "ext": f.get("ext"),
        "hints": f.get("hints", {}),
        "symbols": trimmed_symbols,
        "internal_dependencies": _internal_deps(graph, f["path"])[:10],  # Limit to 10 deps
        "external_dependencies": _external_deps(graph, f["path"])[:10],  # Limit to 10 deps
    }
    
    start_time = time.time()
    try:
        result = await llm.acomplete_json(file_messages(ctx), FILE_SCHEMA)
        duration_ms = (time.time() - start_time) * 1000
        
        # Record successful LLM call
        metrics.record_llm_call("file_summary", llm.model, "success", duration_ms)
        
        # Validate required fields
        if not result.get("title"):
            result["title"] = f["path"].split("/")[-1]
        if not result.get("blurb"):
            result["blurb"] = _generate_file_blurb(f)
        if not result.get("dev_summary"):
            result["dev_summary"] = f"A {f.get('language', 'unknown')} file with {len(f.get('symbols', {}).get('functions', []))} functions."
        if not result.get("vibecoder_summary"):
            result["vibecoder_summary"] = "This file is part of the application."
        return result
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.warning(f"LLM summary failed for {f['path']}: {e}")
        
        # Record failed LLM call
        metrics.record_llm_call("file_summary", llm.model, "error", duration_ms)
        
        # Minimal fallback if LLM fails
        return {
            "title": f["path"].split("/")[-1],
            "purpose": f"A {f.get('language', 'unknown')} file.",
            "key_functions": f.get("symbols", {}).get("functions", [])[:5],
            "internal_dependencies": ctx["internal_dependencies"],
            "external_dependencies": ctx["external_dependencies"],
            "how_to_modify": "Edit this file to modify its functionality.",
            "risks": "Be careful when modifying this file.",
            "blurb": _generate_file_blurb(f),
            "dev_summary": f"A {f.get('language', 'unknown')} file with {len(f.get('symbols', {}).get('functions', []))} functions.",
            "vibecoder_summary": "This file is part of the application.",
            "edit_points": [],
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

def _extract_repo_terms(files_payload: Dict[str, Any]) -> List[str]:
    """Extract repo-specific terms from files for glossary generation."""
    terms = set()
    
    for file_data in files_payload.get("files", []):
        # Extract from hints
        hints = file_data.get("hints", {})
        if hints.get("isRoute"):
            terms.add("route")
        if hints.get("isAPI"):
            terms.add("API")
        if hints.get("isComponent"):
            terms.add("component")
        if hints.get("isService"):
            terms.add("service")
        if hints.get("isMiddleware"):
            terms.add("middleware")
        
        # Extract from symbols
        symbols = file_data.get("symbols", {})
        if symbols.get("hooks"):
            terms.add("hook")
        if symbols.get("components"):
            terms.add("component")
        if symbols.get("dbModels"):
            terms.add("database model")
        if symbols.get("middleware"):
            terms.add("middleware")
        
        # Extract from file extensions
        path = file_data.get("path", "")
        if path.endswith(".test.") or path.endswith(".spec."):
            terms.add("test")
        if path.endswith(".config."):
            terms.add("configuration")
        if path.endswith(".env"):
            terms.add("environment variable")
    
    return list(terms)

async def _build_glossary(llm: LLMClient, files_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build glossary with base terms and repo-specific terms."""
    metrics = get_metrics_collector()
    
    base_terms = [
        "function", "class", "import", "export", "component", "route", "API", "schema",
        "middleware", "service", "controller", "dependency", "module", "queue", "job",
        "provider", "environment variable", "logger", "test", "configuration", "hook",
        "database model", "state", "props", "context", "reducer", "action", "selector"
    ]
    
    # Add repo-specific terms
    repo_terms = _extract_repo_terms(files_payload)
    all_terms = list(set(base_terms + repo_terms))[:50]  # Cap at 50 terms
    
    start_time = time.time()
    try:
        result = await llm.acomplete_json(glossary_messages(all_terms), GLOSSARY_SCHEMA)
        duration_ms = (time.time() - start_time) * 1000
        
        # Record successful LLM call
        metrics.record_llm_call("glossary", llm.model, "success", duration_ms)
        
        # Ensure we have at least some terms
        if not result.get("terms"):
            result["terms"] = []
        return result
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.warning(f"LLM glossary generation failed: {e}")
        
        # Record failed LLM call
        metrics.record_llm_call("glossary", llm.model, "error", duration_ms)
        
        # Fallback to minimal glossary
        return {
            "terms": [
                {"term": "function", "dev_definition": "Reusable block of code.", "vibecoder_definition": "A recipe you can run."},
                {"term": "component", "dev_definition": "A reusable UI element.", "vibecoder_definition": "A building block for your interface."},
                {"term": "API", "dev_definition": "Application Programming Interface.", "vibecoder_definition": "How different parts of software talk to each other."}
            ]
        }

# ---------- public entry ----------

async def run_summarization(repo_dir: Path) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Generate file summaries, capabilities, and glossary. Persist to repo_dir.
    
    This is the main orchestrator for Step 3 LLM summarization.
    """
    logger.info(f"Starting summarization for repo: {repo_dir}")
    
    # Read required files
    files_path = repo_dir / "files.json"
    graph_path = repo_dir / "graph.json"
    
    if not files_path.exists():
        raise FileNotFoundError(f"files.json not found in {repo_dir}")
    
    files_payload = json.loads(files_path.read_text(encoding="utf-8"))
    
    # Graph is optional, provide empty fallback
    if graph_path.exists():
        graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
    else:
        graph_payload = {"edges": []}
        logger.warning(f"graph.json not found in {repo_dir}, using empty graph")
    
    # Initialize LLM client
    llm = LLMClient(cache_dir=repo_dir / "cache_llm")
    files = files_payload.get("files", [])
    idx = _idx_files(files_payload)
    
    # Track metrics
    llm_calls = 0
    llm_cache_hits = 0
    llm_timeouts = 0
    files_summarized = 0
    repo_warnings = []
    
    # ---- Per-file summaries with concurrency control ----
    logger.info(f"Processing {len(files)} files for summaries")
    
    # Filter out skipped files
    non_skipped_files = [f for f in files if not f.get("skipped", False)]
    budget = getattr(settings, 'LLM_FILE_SUMMARY_BUDGET', len(non_skipped_files))
    
    if len(non_skipped_files) > budget:
        logger.warning(f"File count ({len(non_skipped_files)}) exceeds budget ({budget}), processing first {budget}")
        non_skipped_files = non_skipped_files[:budget]
        repo_warnings.append(f"File summary budget exceeded, only processed {budget} files")
    
    # Process files with concurrency control
    semaphore = asyncio.Semaphore(settings.LLM_CONCURRENCY)
    
    async def process_file_with_semaphore(f):
        async with semaphore:
            return await _summ_file(llm, f, graph_payload)
    
    try:
        file_summaries = await asyncio.gather(
            *[process_file_with_semaphore(f) for f in non_skipped_files],
            return_exceptions=True
        )
    except Exception as e:
        logger.error(f"Error in file summarization: {e}")
        file_summaries = []
        repo_warnings.append(f"File summarization failed: {str(e)}")
    
    # Attach summaries to files and ensure required fields
    for i, f in enumerate(non_skipped_files):
        if i < len(file_summaries) and not isinstance(file_summaries[i], Exception):
            summary = file_summaries[i]
            f["summary"] = summary
            f["blurb"] = summary.get("blurb", _generate_file_blurb(f))[:200]  # Truncate to 200 chars
            files_summarized += 1
        else:
            # Fallback for failed files
            f["summary"] = {
                "title": f["path"].split("/")[-1],
                "purpose": f"A {f.get('language', 'unknown')} file.",
                "key_functions": f.get("symbols", {}).get("functions", [])[:5],
                "internal_dependencies": _internal_deps(graph_payload, f["path"])[:10],
                "external_dependencies": _external_deps(graph_payload, f["path"])[:10],
                "how_to_modify": "Edit this file to modify its functionality.",
                "risks": "Be careful when modifying this file.",
                "blurb": _generate_file_blurb(f),
                "vibecoder_summary": "This file is part of the application.",
                "edit_points": [],
            }
            f["blurb"] = f["summary"]["blurb"][:200]
    
    # Update files payload
    files_payload["files"] = files
    files_payload["generatedAt"] = _now()
    if repo_warnings:
        files_payload["warnings"] = repo_warnings
    
    # Atomic write of updated files.json
    write_json_atomic(files_path, files_payload)
    logger.info(f"Updated files.json with {files_summarized} summaries")
    
    # ---- Capabilities generation ----
    logger.info("Generating capabilities")
    try:
        from app.capabilities import build_all_capabilities
        capabilities_payload = await build_all_capabilities(files_payload, graph_payload, repo_dir)
    except Exception as e:
        logger.error(f"Capability generation failed: {e}")
        capabilities_payload = {
            "repoId": files_payload.get("repoId", "unknown"),
            "generatedAt": _now(),
            "capabilities": [],
            "warnings": [f"Capability generation failed: {str(e)}"]
        }
    
    # ---- Glossary generation ----
    logger.info("Generating glossary")
    try:
        glossary_payload = await _build_glossary(llm, files_payload)
        glossary_payload["generatedAt"] = _now()
    except Exception as e:
        logger.error(f"Glossary generation failed: {e}")
        glossary_payload = {
            "terms": [
                {"term": "function", "dev_definition": "Reusable block of code.", "vibecoder_definition": "A recipe you can run."}
            ],
            "generatedAt": _now(),
            "warnings": [f"Glossary generation failed: {str(e)}"]
        }
    
    # Atomic write for glossary only (capabilities are written by build_all_capabilities)
    write_json_atomic(repo_dir / "glossary.json", glossary_payload)
    
    logger.info(f"Summarization complete: {files_summarized} files, {len(capabilities_payload.get('capabilities', []))} capabilities, {len(glossary_payload.get('terms', []))} glossary terms")
    
    return files_payload, capabilities_payload, glossary_payload
