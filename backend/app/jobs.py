from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Dict

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

        try:
            # --- Discovering ---
            store.update(phase="acquiring", pct=10)
            await asyncio.sleep(0.05)

            snapshot = repo_dir / "snapshot"
            store.update(phase="discovering", pct=20)
            discovered = discover_files(snapshot)
            store.update(phase="discovering", pct=30, filesParsed=len(discovered))

            # --- Parsing ---
            store.update(phase="parsing", pct=40)
            files_list, top_warnings = parse_files(snapshot, discovered)
            store.update(phase="parsing", pct=50, filesParsed=len(files_list))

            files_payload = build_files_payload(repo_dir.name, files_list, top_warnings)

            # Persist files.json
            write_json_atomic(repo_dir / "files.json", files_payload)

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

            # --- Summarizing ---
            store.update(phase="summarizing", pct=88)
            files_payload, capabilities_payload, glossary_payload = await run_summarization(repo_dir)
            store.update(
                phase="done", pct=100,
                filesSummarized=len(files_payload.get("files", [])),
                capabilitiesBuilt=len(capabilities_payload.get("capabilities", []))
            )

        except Exception as e:
            store.update(phase="failed", pct=100, error=str(e))

job_queue = JobQueue()
