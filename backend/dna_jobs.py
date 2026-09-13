"""
Engine 01 as a background job.

The crawl takes minutes, so the UI starts a job and polls it instead of holding
one HTTP request open. Everything Engine 01 prints is captured as a live log.
One scrape runs at a time (localhost, single user).
"""

import asyncio
import sys
import time
import traceback
import uuid
from dataclasses import asdict

import database as db
from brand_resolver import resolve_brand
from company_scraper import extract_company_dna

LOG_TAIL = 150

_jobs: dict[str, "DNAJob"] = {}


class DNAJob:
    def __init__(self, query: str):
        self.id = uuid.uuid4().hex[:12]
        self.query = query
        self.status = "running"      # running | success | failed
        self.stage = "resolving"     # resolving | scraping | saving | done
        self.url = ""
        self.resolved_by = ""
        self.logs: list[str] = []
        self.error = ""
        self.result: dict | None = None
        self.started_at = time.time()
        self.finished_at: float | None = None
        self.task: asyncio.Task | None = None

    def log(self, line: str) -> None:
        self.logs.append(line)

    def to_dict(self) -> dict:
        end = self.finished_at or time.time()
        return {
            "id": self.id,
            "query": self.query,
            "status": self.status,
            "stage": self.stage,
            "url": self.url,
            "resolved_by": self.resolved_by,
            "error": self.error,
            "elapsed": round(end - self.started_at),
            "log_count": len(self.logs),
            "logs": self.logs[-LOG_TAIL:],
            "result": self.result,
        }


class _Tee:
    """Mirror stdout to the terminal and into the job log, line by line."""

    def __init__(self, stream, job: DNAJob):
        self._stream = stream
        self._job = job
        self._buf = ""

    def write(self, s: str) -> int:
        try:
            self._stream.write(s)
        except Exception:
            pass
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self._job.log(line.rstrip())
        return len(s)

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def get_job(job_id: str) -> DNAJob | None:
    return _jobs.get(job_id)


def start_job(query: str) -> DNAJob:
    active = next((j for j in _jobs.values() if j.status == "running"), None)
    if active:
        raise RuntimeError(f"A scrape for '{active.query}' is already running")
    job = DNAJob(query)
    _jobs[job.id] = job
    job.task = asyncio.create_task(_run(job))
    return job


async def _run(job: DNAJob) -> None:
    original = sys.stdout
    sys.stdout = _Tee(original, job)
    try:
        print(f"[autopilot] Resolving '{job.query}'")
        info = await resolve_brand(job.query)
        job.url, job.resolved_by = info["url"], info["source"]
        print(f"[autopilot] Website: {job.url} (found via {job.resolved_by})")

        job.stage = "scraping"
        dna = await extract_company_dna(job.url)
        if not dna.services and not dna.about_text and not dna.homepage_text:
            raise RuntimeError(f"No usable content extracted from {job.url} (site may block automated browsers)")

        job.stage = "saving"
        client = await db.create_client(job.url)
        dna_dict = asdict(dna)
        updated = await db.save_dna(client["id"], dna_dict)
        job.result = {"client": updated, "dna": dna_dict}
        job.stage, job.status = "done", "success"
        print(f"[autopilot] DNA saved for {updated.get('name')} → clients/{updated.get('slug')}/01_brand_dna/")
    except Exception as e:
        traceback.print_exc()
        job.status, job.error = "failed", f"{type(e).__name__}: {e}"
    finally:
        sys.stdout = original
        job.finished_at = time.time()
