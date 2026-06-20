"""
CuratorJob -- brain hygiene via review_state transitions.

Reads `brain/system/*.yml` AS-IS (no snapshot needed; this job is
idempotent and self-correcting). For each entry, applies the state
machine:

  active     -- verified within ACTIVE_FRESH_DAYS
  -> stale       -- not verified for STALE_THRESHOLD_DAYS
  -> deprecated  -- still not verified for DEPRECATE_THRESHOLD_DAYS
  -> archived    -- moved to brain/_archived/

Honeymoon grace: first_seen within HONEYMOON_DAYS = no demotion.
Never-archive guards: entries tagged critical/compliance/regulatory/
golden never auto-demote (require manual intervention).

All mutations go through BrainWriter.transition_state / archive,
preserving revision_history and atomic writes.

When to run: time-triggered, default once per 24h. Cursor records
last_run_at; should_run uses that.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .base import Job, JobCursor
from ..system_brain.storage import SystemBrain
from ..system_brain.writer import BrainWriter


# Tunables (could be loaded from config.yml later)
HONEYMOON_DAYS = 60
STALE_THRESHOLD_DAYS = 60
DEPRECATE_THRESHOLD_DAYS = 120
ARCHIVE_THRESHOLD_DAYS = 180
RUN_EVERY_HOURS = 24

NEVER_ARCHIVE_TAGS = {"critical", "compliance", "regulatory", "golden"}


def _parse_iso(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    s = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
    try:
        return datetime.fromisoformat(s).replace(tzinfo=None)
    except Exception:
        return None


def _age_days(ts: str, now: datetime) -> Optional[int]:
    dt = _parse_iso(ts)
    if not dt:
        return None
    return (now - dt).days


class CuratorJob(Job):
    name = "curator"
    needs_snapshot = False     # idempotent, self-correcting

    def should_run(self, cur: JobCursor) -> bool:
        last = _parse_iso(cur.last_run_at)
        if last is None:
            return True
        age_h = (datetime.utcnow() - last).total_seconds() / 3600
        return age_h >= RUN_EVERY_HOURS

    def run(self, cur: JobCursor) -> dict:
        writer = BrainWriter(self.brain_dir)
        brain = SystemBrain(self.brain_dir)
        brain.load()
        now = datetime.utcnow()

        summary = {
            "scanned": 0,
            "honeymoon_protected": 0,
            "never_archive_protected": 0,
            "active_to_stale": 0,
            "stale_to_deprecated": 0,
            "deprecated_to_archived": 0,
            "noop": 0,
        }

        for kind in ("pages", "transitions", "observations"):
            store = getattr(brain, kind)
            for entry_id in list(store.keys()):
                entry = store[entry_id]
                summary["scanned"] += 1
                action = self._decide(entry, now)
                if action is None:
                    summary["noop"] += 1
                    continue

                tag, new_state, reason = action

                if tag == "honeymoon":
                    summary["honeymoon_protected"] += 1
                    continue
                if tag == "never_archive":
                    summary["never_archive_protected"] += 1
                    continue

                if new_state == "archived":
                    r = writer.archive(kind, entry_id, reason)
                    if r.op == "archived":
                        summary["deprecated_to_archived"] += 1
                else:
                    r = writer.transition_state(kind, entry_id, new_state, reason)
                    if r.op == "state_changed":
                        if new_state == "stale":
                            summary["active_to_stale"] += 1
                        elif new_state == "deprecated":
                            summary["stale_to_deprecated"] += 1

        return summary

    # ------------------------------------------------------------------

    def _decide(self, entry, now: datetime):
        """Return None (noop) or (tag, new_state, reason).

        tag is one of: 'demote', 'honeymoon', 'never_archive'
        """
        prov = entry.prov
        # Created date: prefer prov.created_at; fall back to now-on-load
        created_age = _age_days(getattr(prov, "created_at", ""), now)
        last_seen_age = _age_days(
            getattr(prov, "updated_at", "") or getattr(prov, "created_at", ""),
            now,
        )
        # Honeymoon: brand-new, never used much; don't demote.
        if created_age is not None and created_age < HONEYMOON_DAYS:
            return ("honeymoon", "", "within honeymoon window")

        # Never-archive: tag-based protection. We don't have an explicit
        # tags field on schemas; check claim/notes for keywords as a
        # conservative proxy.
        text_blob = (
            (getattr(entry, "title_pattern", "") or "") + " " +
            (getattr(entry, "intent", "") or "") + " " +
            (getattr(entry, "selector", "") or "")
        ).lower()
        if any(t in text_blob for t in NEVER_ARCHIVE_TAGS):
            return ("never_archive", "", "tagged never-archive")

        state = prov.review_state
        age = last_seen_age if last_seen_age is not None else 0

        # State machine
        if state == "active" and age >= STALE_THRESHOLD_DAYS:
            return ("demote", "stale",
                    f"no verification for {age}d (>= {STALE_THRESHOLD_DAYS}d)")
        if state == "stale" and age >= DEPRECATE_THRESHOLD_DAYS:
            return ("demote", "deprecated",
                    f"stale and not refreshed for {age}d")
        if state == "deprecated" and age >= ARCHIVE_THRESHOLD_DAYS:
            return ("demote", "archived",
                    f"deprecated and untouched for {age}d")
        return None


__all__ = ["CuratorJob"]
