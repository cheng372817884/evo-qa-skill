"""
ReflectionJob -- LLM-driven business-layer extraction (Phase 2 stub).

Triggered by run-count delta: when (latest_run_id - cursor.last_reflection_run_id)
crosses a threshold, take a snapshot, call the LLM with the filtered
brain view, and write the proposal to brain/business/_proposed_<snap_id>.yml.

Why count-triggered, not time-triggered:
  - reflection only adds value with new evidence; running on time
    when nothing changed wastes LLM budget
  - a project that runs 50 cases/week needs more reflection than one
    that runs 1 case/week

Why always _proposed and never auto-promoted:
  - business model claims are interpretive; humans must accept
  - corollary: if a proposal is rejected, the rejection itself becomes
    a signal (we record it as a Question)

V1 status: STUB. The LLM call is faked. The mechanism (snapshot +
view_at + write atomically) is real and tested. When a real LLM
adapter lands, plug it into _call_llm().
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Optional

import yaml

from .._atomic import atomic_write
from .base import Job, JobCursor
from .snapshot import take_snapshot, Snapshot
from ..system_brain.storage import SystemBrain


REFLECTION_THRESHOLD_RUNS = 5     # how many new runs before re-reflecting


class ReflectionJob(Job):
    name = "reflection"
    needs_snapshot = True

    def __init__(self, brain_dir: Path, llm_call=None):
        """
        llm_call: callable(brain_view) -> dict, or None to use the stub.
        """
        super().__init__(brain_dir)
        self._llm_call = llm_call or self._stub_llm

    def should_run(self, cur: JobCursor) -> bool:
        # Find the current max run_id; compare with cursor's last.
        snap = take_snapshot(self.brain_dir)
        if not snap.upper_bound:
            return False
        last_seen = cur.extra.get("last_reflection_run_id", "")
        # Count delta: how many new run_ids since last reflection?
        new_runs = max(0, snap.evidence_run_count - cur.runs_seen)
        forced = bool(cur.extra.get("forced_next", False))
        return forced or new_runs >= REFLECTION_THRESHOLD_RUNS

    def run(self, cur: JobCursor) -> dict:
        snap = take_snapshot(self.brain_dir)
        brain = SystemBrain(self.brain_dir)
        brain.load()
        view = brain.view_at(snap)

        proposal = self._llm_call(view)

        out_path = (self.brain_dir / "business" /
                    f"_proposed_{snap.snap_id}.yml")
        payload = {
            "snapshot_basis": snap.snap_id,
            "upper_bound": snap.upper_bound,
            "evidence_run_count": snap.evidence_run_count,
            "view_summary": view.stats(),
            "proposal": proposal,
            "review_state": "proposed",   # NEVER auto-promoted
            "notes": "LLM-generated. Requires human review before promotion.",
        }
        atomic_write(
            out_path,
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True,
                           width=120),
        )

        # Update cursor extras
        cur.runs_seen = snap.evidence_run_count
        cur.last_run_id_seen = snap.upper_bound
        cur.extra["last_reflection_run_id"] = snap.upper_bound
        cur.extra["last_proposal_path"] = str(out_path)
        cur.extra["forced_next"] = False
        # Append history
        history = cur.extra.setdefault("history", [])
        history.append({
            "snap_id": snap.snap_id,
            "upper_bound": snap.upper_bound,
            "proposal": str(out_path),
        })
        # Cap history at 50 entries
        if len(history) > 50:
            cur.extra["history"] = history[-50:]

        return {
            "snap_id": snap.snap_id,
            "upper_bound": snap.upper_bound,
            "view_pages": len(view.pages),
            "view_observations": len(view.observations),
            "proposal_path": str(out_path),
        }

    # ------------------------------------------------------------------
    # Stub LLM (replace via constructor injection)
    # ------------------------------------------------------------------

    @staticmethod
    def _stub_llm(view) -> dict:
        return {
            "domain": "(LLM stub) inferred domain placeholder",
            "entities": [
                {"name": p.title_pattern, "evidence_pages": [pid]}
                for pid, p in list(view.pages.items())[:5]
            ],
            "operations": [
                "(stub) operation 1", "(stub) operation 2",
            ],
            "workflows": [],
            "_note": "This is a stub. Replace with real LLM call.",
        }


__all__ = ["ReflectionJob", "REFLECTION_THRESHOLD_RUNS"]
