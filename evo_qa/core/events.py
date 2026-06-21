"""
Event contracts for the RunBus.

================================================================
SINK vs JOB DICHOTOMY  (read this before adding any new consumer)
================================================================

A RunBus SINK is allowed iff it answers YES to all of:

  - Can it produce useful output from looking at ONE run?
  - Is its operation IDEMPOTENT (re-delivering same event = no harm)?
  - Does it complete in well under 60 seconds?

A consumer that answers NO to any of those is NOT a sink.
It belongs in core/scheduler/ as a Job:

  - Needs to scan all entries OR filter by age window  -> Job
  - Calls slow/expensive APIs (e.g. LLM)               -> Job
  - Aggregates across many runs                        -> Job
  - Triggered by time, not by event                    -> Job

Curator is a Job (time-window scanning).
Reflection is a Job (cross-run aggregation + LLM calls).
ExtractorSink is a Sink (single-run reactive, idempotent by run_id).
LearnSink is a Sink (single-run failure -> heuristic, idempotent).

================================================================
SIZE INVARIANT
================================================================

Every event serialized to events.jsonl MUST be < 4000 bytes so that
O_APPEND remains atomic on Linux. We enforce this with an assert in
to_jsonl(). Events that need more data should reference paths to
files written separately (atomic_write), not embed data inline.

================================================================
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from ._atomic import PIPE_BUF_SAFE


# Soft cap below the hard PIPE_BUF_SAFE so we have headroom for newline,
# encoding overhead, and future field additions.
EVENT_SIZE_SOFT_CAP = 3500


@dataclass
class Event:
    """Base event. Concrete events extend this."""
    id: str = field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    type: str = "event"
    ts_ns: int = field(default_factory=time.time_ns)

    def to_jsonl(self) -> str:
        line = json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))
        if len(line.encode("utf-8")) > EVENT_SIZE_SOFT_CAP:
            raise ValueError(
                f"event {self.id} is {len(line)} bytes; max is "
                f"{EVENT_SIZE_SOFT_CAP}. Reference files by path instead "
                f"of inlining data."
            )
        return line

    @staticmethod
    def from_jsonl(line: str) -> dict[str, Any]:
        return json.loads(line)


@dataclass
class RunCompleted(Event):
    """Emitted by main flow after a run finishes (pass or fail).

    All bulky data lives on disk under run_record_path / evidence_dir.
    Sinks load only what they need.
    """
    type: str = "run.completed"
    project: str = ""
    change_id: str = ""
    run_id: str = ""
    verdict: str = ""              # pass | drift | exploration_failure | system_failure
    build: str = ""
    run_record_path: str = ""      # path to runs/<run_id>.json
    evidence_dir: str = ""         # path to evidence directory
    test_file_path: str = ""       # path to pytest spec, if any
    duration_ms: int = 0


@dataclass
class RunFailed(Event):
    """Emitted by main flow when a run hard-fails before producing
    a normal record (e.g., browser launch failed). Keeps reverse-feed
    informed that something happened, even when there's no record."""
    type: str = "run.failed"
    project: str = ""
    change_id: str = ""
    run_id: str = ""
    error_kind: str = ""
    error_msg: str = ""


__all__ = [
    "Event", "RunCompleted", "RunFailed",
    "EVENT_SIZE_SOFT_CAP",
]
