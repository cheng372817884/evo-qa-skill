"""
BrainWriter — the ONLY code path that mutates brain/system/*.yml.

Concurrency model:
  Two distinct writers exist, with disjoint field ownership:

  +------------------------------+----------------+--------------+
  | Field                        | ExtractorSink  | CuratorJob   |
  +------------------------------+----------------+--------------+
  | id / claim / fact fields     | create+update  | read-only    |
  | prov.evidence                | append (set)   | read-only    |
  | prov.last_verified_run/build | update         | read-only    |
  | prov.confidence              | update         | read-only    |
  | prov.first_seen_*            | set once       | read-only    |
  | values_seen / operations     | append (set)   | read-only    |
  | prov.review_state            | set 'active' on| UNIQUE       |
  |                              | creation only  | writer       |
  | _archived/ directory         | never touch    | UNIQUE       |
  | prov.revision_history        | append on      | append on    |
  |                              | revise         | state change |
  +------------------------------+----------------+--------------+

  revision_history shared-append entries carry (actor, ts_ns) keys;
  BrainWriter dedups + sorts on every save. Last-writer-wins on
  the file as a whole is acceptable because field-level conflicts
  are empty by design.

All writes go through atomic_write (full-file replace via os.replace).
No locks. No partial states visible to readers.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .schemas import (
    PageNode, Transition, FieldObservation,
    Question, Contradiction, Provenance,
)
from .storage import SystemBrain


@dataclass
class WriteResult:
    op: str               # 'new' | 'reinforced' | 'revised' | 'state_changed' | 'archived' | 'noop'
    entry_id: str
    detail: str = ""


class BrainWriter:
    """Mediator over SystemBrain. Use this, not SystemBrain directly,
    for any mutation."""

    def __init__(self, brain_dir: Path):
        self.brain_dir = brain_dir
        self._brain: Optional[SystemBrain] = None

    # --- lifecycle -------------------------------------------------------

    def _load(self) -> SystemBrain:
        # Always reload on each public call. Cheap (small YAML files),
        # ensures we see other process's writes. No caching = no
        # cache-invalidation bugs.
        b = SystemBrain(self.brain_dir)
        b.load()
        self._brain = b
        return b

    def _flush(self, brain: SystemBrain) -> None:
        # Pre-save normalization: dedup revision_history on every entry.
        for store_name in ("pages", "transitions", "observations"):
            store = getattr(brain, store_name)
            for entry in store.values():
                entry.prov.revision_history = self._dedup_history(
                    entry.prov.revision_history
                )
        brain.save()

    @staticmethod
    def _dedup_history(history: list) -> list:
        """Dedup by (actor, ts_ns); preserve order by ts_ns asc."""
        seen = set()
        out = []
        for h in history:
            if not isinstance(h, dict):
                # legacy strings — keep as-is, no key
                out.append(h)
                continue
            key = (h.get("actor", ""), h.get("ts_ns", 0))
            if key in seen:
                continue
            seen.add(key)
            out.append(h)
        # Sort dict entries by ts_ns; non-dict entries stay first
        non_dict = [h for h in out if not isinstance(h, dict)]
        dict_entries = sorted(
            [h for h in out if isinstance(h, dict)],
            key=lambda h: h.get("ts_ns", 0),
        )
        return non_dict + dict_entries

    @staticmethod
    def _history_entry(actor: str, op: str, detail: str = "") -> dict:
        return {
            "actor": actor,           # 'extractor' | 'curator' | 'reflection'
            "op": op,                 # 'created' | 'reinforced' | 'state:active->stale' ...
            "detail": detail,
            "ts_ns": time.time_ns(),
        }

    # =====================================================================
    # ExtractorSink path  -- per-run reactive, idempotent
    # =====================================================================

    def observe_page(self, page: PageNode, run_id: str,
                     build: str = "") -> WriteResult:
        """Idempotent: same run_id observed twice = noop on the 2nd call."""
        brain = self._load()
        # Idempotency guard: if run_id already in evidence, skip.
        existing = brain.pages.get(page.id)
        if existing and run_id in existing.prov.evidence:
            return WriteResult("noop", page.id, f"run {run_id} already recorded")

        op, _node = brain.upsert_page(page, run_id, build)
        # Append history
        node = brain.pages[page.id]
        node.prov.revision_history.append(
            self._history_entry("extractor", op, f"run={run_id}")
        )
        self._flush(brain)
        return WriteResult(op, page.id, f"run={run_id}")

    def observe_transition(self, t: Transition, run_id: str,
                           build: str = "") -> WriteResult:
        brain = self._load()
        existing = brain.transitions.get(t.id)
        if existing and run_id in existing.prov.evidence:
            return WriteResult("noop", t.id)
        op, _ = brain.upsert_transition(t, run_id, build)
        brain.transitions[t.id].prov.revision_history.append(
            self._history_entry("extractor", op, f"run={run_id}")
        )
        self._flush(brain)
        return WriteResult(op, t.id, f"run={run_id}")

    def observe_field(self, obs: FieldObservation, run_id: str,
                      build: str = "") -> WriteResult:
        brain = self._load()
        existing = brain.observations.get(obs.id)
        if existing and run_id in existing.prov.evidence:
            return WriteResult("noop", obs.id)
        op, _ = brain.upsert_observation(obs, run_id, build)
        brain.observations[obs.id].prov.revision_history.append(
            self._history_entry("extractor", op, f"run={run_id}")
        )
        self._flush(brain)
        return WriteResult(op, obs.id, f"run={run_id}")

    def add_question(self, q: Question) -> WriteResult:
        brain = self._load()
        if q.id in brain.questions:
            return WriteResult("noop", q.id)
        brain.add_question(q)
        self._flush(brain)
        return WriteResult("new", q.id)

    def add_contradiction(self, c: Contradiction) -> WriteResult:
        brain = self._load()
        if c.id in brain.contradictions:
            return WriteResult("noop", c.id)
        brain.add_contradiction(c)
        self._flush(brain)
        return WriteResult("new", c.id)

    # =====================================================================
    # CuratorJob path  -- periodic batch, state-only mutations
    # =====================================================================

    _VALID_TRANSITIONS = {
        "active":     {"stale"},
        "stale":      {"active", "deprecated"},
        "deprecated": {"active", "archived"},
        "archived":   {"active"},   # revive
    }

    def transition_state(self, kind: str, entry_id: str,
                         new_state: str, reason: str = "") -> WriteResult:
        """Change review_state. kind ∈ {pages, transitions, observations}.

        Validates the transition is allowed by the state machine.
        Curator + revive both go through here.
        """
        brain = self._load()
        store = getattr(brain, kind, None)
        if store is None or entry_id not in store:
            return WriteResult("noop", entry_id, f"not found in {kind}")

        entry = store[entry_id]
        old = entry.prov.review_state
        if old == new_state:
            return WriteResult("noop", entry_id, f"already {new_state}")
        if new_state not in self._VALID_TRANSITIONS.get(old, set()):
            return WriteResult(
                "noop", entry_id,
                f"invalid transition {old} -> {new_state}"
            )

        entry.prov.review_state = new_state
        entry.prov.revision_history.append(
            self._history_entry("curator", f"state:{old}->{new_state}", reason)
        )
        self._flush(brain)
        return WriteResult("state_changed", entry_id,
                           f"{old} -> {new_state}")

    def archive(self, kind: str, entry_id: str,
                reason: str = "") -> WriteResult:
        """Move entry to _archived/. Goes through transition_state first
        to enforce state machine."""
        # Ensure state is 'archived' first
        r = self.transition_state(kind, entry_id, "archived", reason)
        if r.op == "noop" and "already archived" not in r.detail:
            return r

        # Physically move the entry to _archived/<kind>.yml
        from .._atomic import atomic_write, safe_read
        import yaml
        from .schemas import to_yaml_dict

        brain = self._load()
        store = getattr(brain, kind)
        if entry_id not in store:
            return WriteResult("noop", entry_id, "vanished")

        entry = store.pop(entry_id)
        archived_path = self.brain_dir / "_archived" / f"{kind}.yml"
        existing_archived = []
        if archived_path.exists():
            try:
                existing_archived = yaml.safe_load(safe_read(archived_path)) or []
            except Exception:
                existing_archived = []
        existing_archived.append(to_yaml_dict(entry))
        atomic_write(
            archived_path,
            yaml.safe_dump(existing_archived, sort_keys=False,
                           allow_unicode=True, width=120,
                           default_flow_style=False),
        )
        self._flush(brain)
        return WriteResult("archived", entry_id, f"moved to _archived/{kind}.yml")

    def revive(self, kind: str, entry_id: str,
               reason: str = "") -> WriteResult:
        """Restore from _archived/ back to active. Curator + manual both
        use this."""
        from .._atomic import atomic_write, safe_read
        import yaml

        archived_path = self.brain_dir / "_archived" / f"{kind}.yml"
        if not archived_path.exists():
            return WriteResult("noop", entry_id, "no archive file")
        try:
            archived_data = yaml.safe_load(safe_read(archived_path)) or []
        except Exception:
            return WriteResult("noop", entry_id, "archive file corrupt")

        match = next((d for d in archived_data
                     if d.get("id") == entry_id), None)
        if not match:
            return WriteResult("noop", entry_id, "not in archive")

        # Inflate via SystemBrain.inflate (public reverse of to_yaml_dict)
        brain = self._load()
        revived = brain.inflate(kind, dict(match))
        revived.prov.review_state = "active"
        revived.prov.revision_history.append(
            self._history_entry("curator", "revived", reason)
        )
        getattr(brain, kind)[entry_id] = revived

        # Remove from archive file
        remaining = [d for d in archived_data if d.get("id") != entry_id]
        atomic_write(
            archived_path,
            yaml.safe_dump(remaining, sort_keys=False, allow_unicode=True,
                           width=120, default_flow_style=False),
        )
        self._flush(brain)
        return WriteResult("revived", entry_id, "moved back to active")

    def answer_question(self, qid: str, answer: str,
                        answered_by_run: str = "") -> WriteResult:
        brain = self._load()
        if qid not in brain.questions:
            return WriteResult("noop", qid, "not found")
        q = brain.questions[qid]
        if q.state == "answered":
            return WriteResult("noop", qid, "already answered")
        q.state = "answered"
        q.answer = answer
        q.answered_by_run = answered_by_run
        self._flush(brain)
        return WriteResult("state_changed", qid, "answered")


__all__ = ["BrainWriter", "WriteResult"]
