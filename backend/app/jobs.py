from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Dict, Any
from time import perf_counter

from .status import StatusStore
from .parsers.base import discover_files, parse_files, build_files_payload, build_graph
from .utils.io import write_json_atomic
from .summarizer import run_summarization
from .models import FileNodeModel

class JobQueue:
    def __init__(self):
        self.q: asyncio.Queue[tuple[str, Path]] = asyncio.Queue()
        self._tasks: Dict[str, asyncio.Task] = {}

    async def start_worker(self):
        while True:
            jobId, repo_dir = await self.q.get()
            try:
                await self._run_job(jobId, repo_dir)
            finally:
                self.q.task_done()

    async def enqueue(self, jobId: str, repo_dir: Path):
        await self.q.put((jobId, repo_dir))

    async def _run_job(self, jobId: str, repo_dir: Path):
        store = StatusStore(repo_dir)
        cur = store.read()
        cur.jobId = jobId
        store.update(jobId=jobId)

        t0 = perf_counter()
        metrics: Dict[str, Any] = {
            "jobId": jobId,
            "repoId": repo_dir.name,
            "phaseDurationsMs": {},
        }

        try:
            # --- Phase 1: Discovering (Stream early results) ---
            store.update(phase="acquiring", pct=5)
            await asyncio.sleep(0.05)

            snapshot = repo_dir / "snapshot"
            store.update(phase="discovering", pct=15)
            discovered = discover_files(snapshot)
            
            # Stream early tree structure
            store.update(phase="discovering", pct=25, filesParsed=len(discovered))
            
            # Build and persist basic tree structure early
            def _build_early_tree(discovered_files: list) -> Dict[str, Any]:
                root: Dict[str, Any] = {"id": "root", "path": "/", "purpose": "Repository", "children": []}
                folders: Dict[str, Dict[str, Any]] = {"/": root}

                def folder_purpose(name: str) -> str:
                    n = name.lower()
                    if n in ("app", "src/app"): return "UI routes (Next.js)"
                    if n == "pages": return "Next.js legacy pages + API routes"
                    if n == "api": return "API routes"
                    if n == "lib": return "Libraries / utilities"
                    if n == "components": return "UI components"
                    if n == "workers" or "worker" in n: return "Background workers"
                    if n == "services": return "Business logic / services"
                    if n == "routes": return "Server routes"
                    if n == "templates": return "Rendering templates"
                    if n == "content": return "Static content"
                    if n == "styles" or n == "css": return "Styling"
                    if n == "prisma": return "Database schema"
                    return ""

                for f in discovered_files:
                    path = f.get("path", "")
                    parts = path.split("/")
                    cur_path = "/"
                    parent = root
                    for i, seg in enumerate(parts[:-1]):
                        cur_path = (cur_path.rstrip("/") + "/" + seg).lstrip("/")
                        cur_key = "/" + cur_path if not cur_path.startswith("/") else cur_path
                        if cur_key not in folders:
                            node = {"id": cur_key.strip("/"), "path": seg, "purpose": folder_purpose(seg), "children": []}
                            folders[cur_key] = node
                            parent["children"].append(node)
                        parent = folders[cur_key]
                    # file leaf (basic info only)
                    file_node = {
                        "id": path,
                        "path": path,
                        "purpose": f"File ({f.get('language', 'unknown')})",
                        "exports": [],
                        "imports": [],
                        "functions": [],
                    }
                    parent["children"].append(file_node)

                return root

            # Persist early tree structure
            early_tree = _build_early_tree(discovered)
            write_json_atomic(repo_dir / "tree.json", early_tree)

            t_discover = perf_counter()
            metrics["phaseDurationsMs"]["discovering"] = int((t_discover - t0) * 1000)

            # --- Phase 2: Parsing (Stream functions/classes) ---
            store.update(phase="parsing", pct=35)
            files_list, top_warnings = parse_files(snapshot, discovered)
            
            # Validate parsed files against schema
            validation_warnings = []
            for i, file_entry in enumerate(files_list):
                try:
                    # Validate against FileNodeModel schema
                    FileNodeModel(**file_entry)
                except Exception as e:
                    validation_warnings.append(f"Schema validation failed for {file_entry.get('path', 'unknown')}: {str(e)}")
                    # Mark as skipped if validation fails
                    file_entry["skipped"] = True
                    file_entry["skipReason"] = "schema_validation_failed"
                    file_entry["warnings"] = file_entry.get("warnings", []) + [f"Schema validation failed: {str(e)}"]
            
            if validation_warnings:
                top_warnings.extend(validation_warnings)
            
            store.update(phase="parsing", pct=45, filesParsed=len(files_list))

            # Stream basic files.json with functions/classes
            files_payload = build_files_payload(repo_dir.name, files_list, top_warnings)
            write_json_atomic(repo_dir / "files.json", files_payload)

            t_parse = perf_counter()
            metrics["phaseDurationsMs"]["parsing"] = int((t_parse - t_discover) * 1000)

            # --- Phase 3: Mapping (Stream graph edges) ---
            store.update(phase="mapping", pct=55)
            
            # Update tree.json with detailed file information
            def _build_detailed_tree(files_payload: Dict[str, Any]) -> Dict[str, Any]:
                root: Dict[str, Any] = {"id": "root", "path": "/", "purpose": "Repository", "children": []}
                folders: Dict[str, Dict[str, Any]] = {"/": root}

                def folder_purpose(name: str) -> str:
                    n = name.lower()
                    if n in ("app", "src/app"): return "UI routes (Next.js)"
                    if n == "pages": return "Next.js legacy pages + API routes"
                    if n == "api": return "API routes"
                    if n == "lib": return "Libraries / utilities"
                    if n == "components": return "UI components"
                    if n == "workers" or "worker" in n: return "Background workers"
                    if n == "services": return "Business logic / services"
                    if n == "routes": return "Server routes"
                    if n == "templates": return "Rendering templates"
                    if n == "content": return "Static content"
                    if n == "styles" or n == "css": return "Styling"
                    if n == "prisma": return "Database schema"
                    return ""

                for f in files_payload.get("files", []):
                    path = f.get("path", "")
                    parts = path.split("/")
                    cur_path = "/"
                    parent = root
                    for i, seg in enumerate(parts[:-1]):
                        cur_path = (cur_path.rstrip("/") + "/" + seg).lstrip("/")
                        cur_key = "/" + cur_path if not cur_path.startswith("/") else cur_path
                        if cur_key not in folders:
                            node = {"id": cur_key.strip("/"), "path": seg, "purpose": folder_purpose(seg), "children": []}
                            folders[cur_key] = node
                            parent["children"].append(node)
                        parent = folders[cur_key]
                    # file leaf with detailed info
                    file_node = {
                        "id": path,
                        "path": path,
                        "purpose": f.get("purpose") or f.get("blurb") or "",
                        "exports": f.get("exports", []),
                        "imports": [imp.get("resolved") or imp.get("raw") for imp in f.get("imports", [])],
                        "functions": f.get("summary", {}).get("key_functions", []) or [],
                    }
                    parent["children"].append(file_node)

                return root

            # Update tree with detailed information
            detailed_tree = _build_detailed_tree(files_payload)
            write_json_atomic(repo_dir / "tree.json", detailed_tree)
            
            store.update(phase="mapping", pct=65)
            
            # Build and stream graph
            graph_payload = build_graph(files_payload)
            write_json_atomic(repo_dir / "graph.json", graph_payload)

            # Calculate detailed import metrics
            edges = graph_payload.get("edges", [])
            imports_total = len(edges)
            imports_internal = sum(1 for edge in edges if not edge.get("external", True))
            imports_external = imports_total - imports_internal

            # Merge graph warnings with existing warnings
            graph_warnings = graph_payload.get("warnings", [])
            all_warnings = top_warnings + graph_warnings

            # Update status with detailed metrics and warnings
            store.update(
                phase="mapping", pct=75,
                imports=imports_total,  # Backward compatibility
                importsTotal=imports_total,
                importsInternal=imports_internal,
                importsExternal=imports_external,
                warnings=all_warnings
            )

            metrics.update({
                "filesCount": len(files_list),
                "importsTotal": imports_total,
                "importsInternal": imports_internal,
                "importsExternal": imports_external,
                "warningsCount": len(all_warnings),
            })
            t_map = perf_counter()
            metrics["phaseDurationsMs"]["mapping"] = int((t_map - t_parse) * 1000)

            # --- Phase 4: Summarizing (Stream LLM summaries) ---
            store.update(phase="summarizing", pct=85)
            files_payload, capabilities_payload, glossary_payload = await run_summarization(repo_dir)
            
            # Stream capabilities as they're generated
            store.update(phase="summarizing", pct=95, 
                        filesSummarized=len(files_payload.get("files", [])),
                        capabilitiesBuilt=len(capabilities_payload.get("capabilities", [])))
            
            store.update(
                phase="done", pct=100,
                filesSummarized=len(files_payload.get("files", [])),
                capabilitiesBuilt=len(capabilities_payload.get("capabilities", []))
            )

            t_end = perf_counter()
            metrics["totalMs"] = int((t_end - t0) * 1000)
            write_json_atomic(repo_dir / "metrics.json", metrics)

        except Exception as e:
            store.update(phase="failed", pct=100, error=str(e))
        finally:
            # Ensure tree.json exists if files.json is present (for older repos or early failures)
            try:
                files_path = repo_dir / "files.json"
                tree_path = repo_dir / "tree.json"
                if files_path.exists() and not tree_path.exists():
                    files_payload = json.loads(files_path.read_text())
                    # build a minimal tree
                    root = {"id": "root", "path": "/", "purpose": "Repository", "children": []}
                    folders: Dict[str, Any] = {"/": root}
                    for f in files_payload.get("files", []):
                        p = f.get("path", "")
                        parts = p.split("/")
                        parent = root
                        cur = ""
                        for seg in parts[:-1]:
                            cur = (cur + "/" + seg).lstrip("/")
                            key = "/" + cur
                            if key not in folders:
                                node = {"id": cur, "path": seg, "purpose": "", "children": []}
                                folders[key] = node
                                parent["children"].append(node)
                            parent = folders[key]
                        parent["children"].append({
                            "id": p, "path": p, "purpose": f.get("purpose") or f.get("blurb") or "",
                            "exports": f.get("exports", []),
                            "imports": [imp.get("resolved") or imp.get("raw") for imp in f.get("imports", [])],
                            "functions": f.get("summary", {}).get("key_functions", []) or [],
                        })
                    write_json_atomic(tree_path, root)
            except Exception:
                pass

            # Ensure metrics.json exists with at least basic fields
            try:
                import json as _json
                metrics_path = repo_dir / "metrics.json"
                if not metrics_path.exists():
                    # attempt to compute basic metrics from existing artifacts
                    files_path = repo_dir / "files.json"
                    graph_path = repo_dir / "graph.json"
                    files_count = 0
                    imports_total = imports_internal = imports_external = 0
                    if files_path.exists():
                        files_count = len(_json.loads(files_path.read_text()).get("files", []))
                    if graph_path.exists():
                        edges = _json.loads(graph_path.read_text()).get("edges", [])
                        imports_total = len(edges)
                        imports_internal = sum(1 for e in edges if not e.get("external", True))
                        imports_external = imports_total - imports_internal
                    write_json_atomic(metrics_path, {
                        "filesCount": files_count,
                        "importsTotal": imports_total,
                        "importsInternal": imports_internal,
                        "importsExternal": imports_external,
                        "phaseDurationsMs": metrics.get("phaseDurationsMs", {}),
                        "totalMs": metrics.get("totalMs", 0),
                    })
            except Exception:
                pass
            
            # Ensure capabilities index exists with stable shape
            try:
                caps_dir = repo_dir / "capabilities"
                index_path = caps_dir / "index.json"
                if not index_path.exists():
                    caps_dir.mkdir(exist_ok=True)
                    write_json_atomic(index_path, {"index": []})
            except Exception:
                pass

job_queue = JobQueue()
