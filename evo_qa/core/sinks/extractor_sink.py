"""
ExtractorSink -- per-run reactive sink that feeds the system brain.

Triggered by run.completed events. Idempotent by run_id (BrainWriter
checks evidence membership before each upsert).

Reads from disk:
  - run_record_path  (runs/<run_id>.json)
  - test_file_path   (optional; pytest spec for legacy reverse-extraction)

Writes through BrainWriter (the only sanctioned path for brain/system/*.yml).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import Sink
from ..system_brain.extractor import Extractor, TraceEvent
from ..system_brain.legacy import parse_test_file
from ..system_brain.storage import SystemBrain
from ..system_brain.writer import BrainWriter


class ExtractorSink(Sink):
    name = "extractor"
    accepts = ("run.completed",)

    def __init__(self, brain_dir: Path):
        self.brain_dir = brain_dir
        self.writer = BrainWriter(brain_dir)

    def handle(self, event: dict[str, Any]) -> None:
        run_id = event.get("run_id") or ""
        build = event.get("build") or ""
        if not run_id:
            raise ValueError("run.completed event missing run_id")

        # Load trace events. Two sources, in priority:
        #   1. run_record_path with per-atom trace (v1.x runs)
        #   2. test_file_path  (legacy reverse-extraction)
        trace_events = self._load_trace_events(event)
        if not trace_events:
            # Nothing to learn from -- not an error, just a no-op.
            return

        # Run the extractor through BrainWriter so writes go through the
        # mediator. The extractor itself uses SystemBrain in-memory; we
        # then replay its mutations through BrainWriter.
        brain = SystemBrain(self.brain_dir)
        brain.load()
        ex = Extractor(brain)
        report = ex.ingest(trace_events, run_id=run_id, build=build)

        # Now persist via BrainWriter for atomic + history bookkeeping.
        # We re-run the public observe_* methods which will be no-ops
        # for already-recorded run_ids (idempotent guarantee).
        for page in brain.pages.values():
            self.writer.observe_page(page, run_id=run_id, build=build)
        for trans in brain.transitions.values():
            self.writer.observe_transition(trans, run_id=run_id, build=build)
        for obs in brain.observations.values():
            self.writer.observe_field(obs, run_id=run_id, build=build)
        for q in brain.questions.values():
            self.writer.add_question(q)
        for c in brain.contradictions.values():
            self.writer.add_contradiction(c)

        # Sanity: report attached to event for tests / observability
        event["_extractor_report"] = report

    # ------------------------------------------------------------------
    # Loading trace events
    # ------------------------------------------------------------------

    def _load_trace_events(self, event: dict[str, Any]) -> list[TraceEvent]:
        # Try run record first (future v1.x will carry per-atom trace)
        rrp = event.get("run_record_path") or ""
        if rrp and Path(rrp).exists():
            evs = self._from_run_record(Path(rrp))
            if evs:
                return evs

        # Fallback: reverse-extract from pytest spec
        tfp = event.get("test_file_path") or ""
        if tfp and Path(tfp).exists():
            return parse_test_file(Path(tfp))

        return []

    @staticmethod
    def _from_run_record(path: Path) -> list[TraceEvent]:
        """Parse a v1.0 run record into TraceEvents. Current run records
        only carry summary stats per step; we extract what we can."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        steps = data.get("steps") or []
        out: list[TraceEvent] = []
        for s in steps:
            atom = s.get("atom", "")
            if not atom:
                continue
            out.append(TraceEvent(
                atom=atom,
                target=s.get("target", "") or "",
                value=s.get("value", "") or "",
                ok=bool(s.get("ok", False)),
                page_title_before=s.get("page_title_before", "") or "",
                page_title_after=s.get("page_title_after", "") or "",
                url_before=s.get("url_before", "") or "",
                url_after=s.get("url_after", "") or "",
                wall_ms=int(s.get("wall_ms", 0) or 0),
                notes=s.get("notes", "") or "",
            ))
        return out


__all__ = ["ExtractorSink"]
