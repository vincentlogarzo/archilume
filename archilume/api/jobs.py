"""In-memory single-job manager for the archilume engine API."""

from __future__ import annotations

import io
import sys
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class JobRecord:
    job_id: str
    status: str = "pending"  # pending | running | done | failed
    phase: str | None = None
    log_lines: list[str] = field(default_factory=list)
    error: str | None = None
    result: dict | None = None
    _thread: threading.Thread | None = field(default=None, repr=False)


class _LogCapture(io.TextIOBase):
    """Captures writes to stdout and appends each line to the job record."""

    def __init__(self, record: JobRecord, original: io.TextIOBase):
        self._record = record
        self._original = original

    def write(self, s: str) -> int:
        if s and s.strip():
            self._record.log_lines.append(s.rstrip())
        return self._original.write(s)

    def flush(self) -> None:
        self._original.flush()


class JobManager:
    """Manages a single background job at a time."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def is_busy(self) -> bool:
        with self._lock:
            return any(j.status in ("pending", "running") for j in self._jobs.values())

    def submit(self, fn: Callable[..., Any], args: tuple = (), kwargs: dict | None = None) -> JobRecord:
        """Submit a job. Raises RuntimeError if a job is already running."""
        if self.is_busy():
            raise RuntimeError("A job is already running")

        record = JobRecord(job_id=uuid.uuid4().hex[:12])
        self._jobs[record.job_id] = record

        def _run() -> None:
            record.status = "running"
            old_stdout = sys.stdout
            sys.stdout = _LogCapture(record, old_stdout)
            try:
                fn(*args, **(kwargs or {}))
                record.status = "done"
                record.result = {"completed": True}
            except Exception as exc:
                record.status = "failed"
                record.error = f"{type(exc).__name__}: {exc}"
                record.log_lines.append(traceback.format_exc())
            finally:
                sys.stdout = old_stdout

        thread = threading.Thread(target=_run, daemon=True)
        record._thread = thread
        thread.start()
        return record

    def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def list_all(self) -> list[JobRecord]:
        return list(self._jobs.values())


# Module-level singleton
job_manager = JobManager()
