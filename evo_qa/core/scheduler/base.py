"""
Job base contract for periodic batch tasks.

A Job is the counterpart to a Sink:

  - Sink: per-event reactive (RunBus consumer), idempotent, fast
  - Job:  time/count-triggered batch, may be slow, snapshot-aware

Each Job has:
  - name: unique identifier (used for cursor file naming)
  - needs_snapshot: bool flag. True for reflection (must see consistent
                    point-in-time view); False for curator (idempotent +
                    self-correcting, reads brain AS-IS).

Each Job decides itself whether to run NOW (via `should_run`) given a
cursor of last-run state. The scheduler calls `should_run` then `run`.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from .._atomic import atomic_write, safe_read


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@dataclass
class JobCursor:
    """Persisted state for a Job. Atomically written. Shape per-job
    is conventional; jobs may add custom fields via `extra`."""
    job_name: str
    last_run_at: str = ""
    last_run_id_seen: str = ""
    runs_seen: int = 0
    success_count: int = 0
    failure_count: int = 0
    extra: dict = field(default_factory=dict)


@dataclass
class JobResult:
    job_name: str
    ran: bool                # did the job actually do work?
    started_at: str = ""
    finished_at: str = ""
    summary: dict = field(default_factory=dict)
    error: Optional[str] = None


class Job(ABC):
    name: str = "unnamed"
    needs_snapshot: bool = False

    def __init__(self, brain_dir: Path):
        self.brain_dir = brain_dir
        self.cursor_path = (brain_dir / ".scheduler" /
                            f"{self.name}_cursor.yml")

    # ------------------------------------------------------------------
    # Cursor I/O
    # ------------------------------------------------------------------

    def load_cursor(self) -> JobCursor:
        raw = safe_read(self.cursor_path, "")
        if not raw:
            return JobCursor(job_name=self.name)
        try:
            data = yaml.safe_load(raw) or {}
            return JobCursor(**data)
        except Exception:
            return JobCursor(job_name=self.name)

    def save_cursor(self, cur: JobCursor) -> None:
        atomic_write(
            self.cursor_path,
            yaml.safe_dump(asdict(cur), sort_keys=False, allow_unicode=True),
        )

    # ------------------------------------------------------------------
    # Job lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def should_run(self, cur: JobCursor) -> bool:
        """Decide if it's time to run now."""

    @abstractmethod
    def run(self, cur: JobCursor) -> dict:
        """Do the work. Return a summary dict. May mutate cur."""

    def execute(self) -> JobResult:
        """Wrapper used by the scheduler runner. Handles cursor I/O,
        timing, and error capture. NEVER raises."""
        result = JobResult(job_name=self.name, ran=False, started_at=_utc_now())
        try:
            cur = self.load_cursor()
            if not self.should_run(cur):
                result.finished_at = _utc_now()
                return result
            summary = self.run(cur)
            cur.last_run_at = _utc_now()
            cur.success_count += 1
            self.save_cursor(cur)
            result.ran = True
            result.summary = summary
        except Exception as e:
            import traceback
            result.error = f"{type(e).__name__}: {e}"
            try:
                cur = self.load_cursor()
                cur.failure_count += 1
                self.save_cursor(cur)
            except Exception:
                pass
        result.finished_at = _utc_now()
        return result


def run_due_jobs(jobs: list[Job]) -> list[JobResult]:
    """Convenience: execute every job whose should_run returns True.
    Used by the scheduler entry point."""
    return [j.execute() for j in jobs]


__all__ = ["Job", "JobCursor", "JobResult", "run_due_jobs"]
