from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Dict, Any
from time import perf_counter

from .status import StatusStore
from .parsers.base import discover_files, parse_files, build_files_payload, build_graph
from .utils.io import write_json_atomic
from .summarizer import run_summarization

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
        store.write(cur)

        t0 = perf_counter()
        metrics: Dict[str, Any] = {
            "jobId": jobId,
            "repoId": repo_dir.name,
            "phaseDurationsMs": {},
        }

        try:
            # --- Discovering ---
            store.update(phase="acquiring", pct=10)
            await asyncio.sleep(0.05)

            snapshot = repo_dir / "snapshot"
            store.update(phase="discovering", pct=20)
            discovered = discover_files(snapshot)
            store.update(phase="discovering", pct=30, filesParsed=len(discovered))

            t_discover = perf_counter()
            metrics["phaseDurationsMs"]["discovering"] = int((t_discover - t0) * 1000)

            # --- Parsing ---
            store.update(phase="parsing", pct=40)
            files_list, top_warnings = parse_files(snapshot, discovered)
            store.update(phase="parsing", pct=50, filesParsed=len(files_list))

            t_parse = perf_counter()
            metrics["phaseDurationsMs"]["parsing"] = int((t_parse - t_discover) * 1000)

            files_payload = build_files_payload(repo_dir.name, files_list, top_warnings)

            # Persist files.json
            write_json_atomic(repo_dir / "files.json", files_payload)

            # --- Build and persist tree.json (hierarchical view) ---
            def _build_tree(files_payload: Dict[str, Any]) -> Dict[str, Any]:
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
                    # file leaf
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

            tree_payload = _build_tree(files_payload)
            write_json_atomic(repo_dir / "tree.json", tree_payload)

            # --- Mapping ---
            store.update(phase="mapping", pct=60)
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

            # --- Summarizing ---
            store.update(phase="summarizing", pct=88)
            files_payload, capabilities_payload, glossary_payload = await run_summarization(repo_dir)
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
