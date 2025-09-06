import asyncio
from pathlib import Path
from typing import Dict
from .status import StatusStore

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

        async def phase(name: str, pct: int, delay: float):
            store.update(phase=name, pct=pct)
            await asyncio.sleep(delay)

        await phase("acquiring", 10, 0.2)
        await phase("discovering", 30, 0.4)
        await phase("parsing", 55, 0.4)
        await phase("mapping", 75, 0.4)
        await phase("summarizing", 90, 0.3)
        store.update(phase="done", pct=100)

job_queue = JobQueue()
