"""
System brain storage — load, save, merge.

Each project has a brain/system/ directory:
  pages.yml
  transitions.yml
  observations.yml      # field observations
  questions.yml
  contradictions.yml
  _digest.md            # human-readable summary

This module is pure data — it doesn't know HOW observations get
extracted from runs. That's `extractor.py`'s job.
"""
from __future__ import annotations

import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional

from .schemas import (
    PageNode, Transition, FieldObservation, Question, Contradiction,
    Provenance, to_yaml_dict, _clean,
)


# Files we manage (in order of how they're typically read)
FILES = ("pages", "transitions", "observations", "questions", "contradictions")


class SystemBrain:
    """In-memory representation of brain/system/."""

    def __init__(self, brain_dir: Path):
        # Convention: brain_dir is the project's brain/ root.
        # System-level YAML lives under brain_dir/system/.
        # Other peers (business/, _archived/, .snapshots/, .bus/, .scheduler/)
        # are siblings of system/.
        brain_dir = Path(brain_dir)
        self.brain_dir = brain_dir
        self.dir = brain_dir / "system"
        self.dir.mkdir(parents=True, exist_ok=True)

        self.pages: dict[str, PageNode] = {}
        self.transitions: dict[str, Transition] = {}
        self.observations: dict[str, FieldObservation] = {}
        self.questions: dict[str, Question] = {}
        self.contradictions: dict[str, Contradiction] = {}

    # -- I/O ---------------------------------------------------------------

    def load(self) -> None:
        for kind in FILES:
            path = self.dir / f"{kind}.yml"
            if not path.exists():
                continue
            data = yaml.safe_load(path.read_text()) or []
            store = getattr(self, kind)
            store.clear()
            for item in data:
                obj = self.inflate(kind, item)
                if obj is not None:
                    store[obj.id] = obj

    def save(self) -> None:
        from .._atomic import atomic_write
        for kind in FILES:
            store = getattr(self, kind)
            path = self.dir / f"{kind}.yml"
            data = [to_yaml_dict(v) for v in store.values()]
            atomic_write(
                path,
                yaml.safe_dump(data, sort_keys=False, allow_unicode=True,
                               width=120, default_flow_style=False),
            )

    def inflate(self, kind: str, data: dict):
        """Public: reverse of to_yaml_dict. Used by BrainWriter.revive().
        Returns a domain object (PageNode / Transition / ...) given
        its dict form."""
        if kind == "pages":
            prov = Provenance(**data.pop("prov", {}))
            return PageNode(prov=prov, **data)
        if kind == "transitions":
            prov = Provenance(**data.pop("prov", {}))
            return Transition(prov=prov, **data)
        if kind == "observations":
            prov = Provenance(**data.pop("prov", {}))
            return FieldObservation(prov=prov, **data)
        if kind == "questions":
            return Question(**data)
        if kind == "contradictions":
            return Contradiction(**data)
        return None

    # -- Merge / upsert (this is the heart of "self-correction") ----------

    def upsert_page(self, node: PageNode, run_id: str,
                    build: str = "") -> tuple[str, PageNode]:
        """Returns ('new'|'reinforced'|'revised', the_node)."""
        existing = self.pages.get(node.id)
        if existing is None:
            node.prov.first_seen_run = run_id
            node.prov.last_verified_run = run_id
            if build:
                node.prov.first_seen_build = build
                node.prov.last_verified_build = build
            node.prov.evidence = [run_id]
            node.prov.confidence = 0.5     # observed once = neutral
            self.pages[node.id] = node
            return ("new", node)

        # Title pattern changed? That's a revision (possible UI rename)
        if (node.title_pattern and
                existing.title_pattern and
                node.title_pattern != existing.title_pattern and
                node.title_pattern not in existing.title_aliases):
            existing.title_aliases.append(existing.title_pattern)
            existing.prov.revise(
                from_value=existing.title_pattern,
                to_value=node.title_pattern,
                reason="page title text drifted",
                run_id=run_id,
            )
            existing.title_pattern = node.title_pattern
            existing.prov.reinforce(run_id, build)
            return ("revised", existing)

        # Merge new key elements (don't drop old ones)
        for k in node.key_elements:
            if k not in existing.key_elements:
                existing.key_elements.append(k)
        existing.prov.reinforce(run_id, build)
        return ("reinforced", existing)

    def upsert_transition(self, t: Transition, run_id: str,
                          build: str = "") -> tuple[str, Transition]:
        existing = self.transitions.get(t.id)
        if existing is None:
            t.prov.first_seen_run = run_id
            t.prov.last_verified_run = run_id
            if build:
                t.prov.first_seen_build = build
                t.prov.last_verified_build = build
            t.prov.evidence = [run_id]
            t.prov.confidence = 0.5
            self.transitions[t.id] = t
            return ("new", t)
        # Merge trigger atoms
        for a in t.trigger_atoms:
            if a not in existing.trigger_atoms:
                existing.trigger_atoms.append(a)
        existing.prov.reinforce(run_id, build)
        return ("reinforced", existing)

    def upsert_observation(self, obs: FieldObservation, run_id: str,
                           build: str = "") -> tuple[str, FieldObservation]:
        existing = self.observations.get(obs.id)
        if existing is None:
            obs.prov.first_seen_run = run_id
            obs.prov.last_verified_run = run_id
            if build:
                obs.prov.first_seen_build = build
                obs.prov.last_verified_build = build
            obs.prov.evidence = [run_id]
            obs.prov.confidence = 0.5
            self.observations[obs.id] = obs
            return ("new", obs)
        # Accumulate
        before_values = list(existing.values_seen)
        for v in obs.values_seen:
            if v not in existing.values_seen:
                existing.values_seen.append(v)
        for op in obs.operations_seen:
            if op not in existing.operations_seen:
                existing.operations_seen.append(op)
        for q in obs.quirks:
            if q not in existing.quirks:
                existing.quirks.append(q)
        for lab in obs.label_seen:
            if lab not in existing.label_seen:
                existing.label_seen.append(lab)
        if existing.values_seen != before_values:
            # New value seen — that's actually a (mild) reinforcement
            # because it widens our coverage. We add the values_seen
            # as part of evidence, not just confirm the same datapoint.
            pass
        existing.prov.reinforce(run_id, build)
        return ("reinforced", existing)

    def add_question(self, q: Question) -> Question:
        if q.id in self.questions:
            return self.questions[q.id]
        self.questions[q.id] = q
        return q

    def add_contradiction(self, c: Contradiction) -> Contradiction:
        self.contradictions[c.id] = c
        # Demote the affected entry
        for store in (self.pages, self.transitions, self.observations):
            if c.affected_entry in store:
                entry = store[c.affected_entry]
                entry.prov.contradicts.append(c.id)
                entry.prov.review_state = "stale"
                entry.prov.confidence = max(0.1, entry.prov.confidence - 0.4)
        return c

    # -- Stats / digest helpers --------------------------------------------

    def stats(self) -> dict:
        def by_state(store):
            out = {"active": 0, "stale": 0, "deprecated": 0, "archived": 0}
            for v in store.values():
                out[v.prov.review_state] = out.get(v.prov.review_state, 0) + 1
            return out

        return {
            "pages": {"total": len(self.pages), **by_state(self.pages)},
            "transitions": {"total": len(self.transitions),
                            **by_state(self.transitions)},
            "observations": {"total": len(self.observations),
                             **by_state(self.observations)},
            "questions": {
                "total": len(self.questions),
                "open": sum(1 for q in self.questions.values()
                            if q.state == "open"),
                "answered": sum(1 for q in self.questions.values()
                                if q.state == "answered"),
            },
            "contradictions": {
                "total": len(self.contradictions),
                "unresolved": sum(1 for c in self.contradictions.values()
                                  if not c.resolved),
            },
        }

    # -- Snapshot view ----------------------------------------------------

    def view_at(self, snapshot) -> "BrainView":
        """Return a filtered, read-only view of this brain "as of" the
        given snapshot's upper_bound run_id.

        For each entry:
          - If first_seen_run > upper_bound  -> excluded (didn't exist yet)
          - Else                              -> included with evidence
            filtered to runs <= upper_bound and confidence recomputed
            from filtered evidence count.
        """
        return BrainView(self, snapshot)


class BrainView:
    """Read-only point-in-time view. Constructed via SystemBrain.view_at().

    Does not copy data. Filters lazily on access. The underlying brain
    may continue to be mutated by other writers; this view's logical
    contents are invariant once constructed (because filtering by
    upper_bound is monotonic).
    """

    def __init__(self, brain: "SystemBrain", snapshot):
        self._brain = brain
        self._snap = snapshot

    def _filter_entry(self, entry):
        """Return None if excluded; else a shallow-cloned entry with
        evidence/confidence recomputed."""
        upper = self._snap.upper_bound
        if not upper:
            return None  # empty snapshot covers nothing

        prov = entry.prov
        first = prov.first_seen_run
        if first and first > upper:
            return None

        filtered_evidence = [r for r in prov.evidence if r <= upper]
        if not filtered_evidence:
            return None  # entry exists but no evidence within bound

        # Shallow clone via dataclass replace on the prov; keep entry id.
        from dataclasses import replace
        new_conf = min(0.95, 0.5 + 0.05 * len(filtered_evidence))
        # Truncate revision_history to events ≤ upper_bound by ts_ns
        # (we don't have run_id->ts_ns mapping; keep history items whose
        # detail mentions a run within bound, fall back to keeping all
        # if can't decide -- conservative).
        new_history = []
        for h in prov.revision_history:
            if not isinstance(h, dict):
                new_history.append(h)
                continue
            detail = h.get("detail", "")
            # crude but workable: keep if no run_id mentioned, or
            # mentioned run_id is within bound
            import re as _re
            m = _re.search(r"run=([\w.-]+)", detail)
            if m and m.group(1) > upper:
                continue
            new_history.append(h)

        new_prov = replace(
            prov,
            evidence=filtered_evidence,
            confidence=new_conf,
            last_verified_run=filtered_evidence[-1] if filtered_evidence
                              else prov.last_verified_run,
            revision_history=new_history,
        )
        return replace(entry, prov=new_prov)

    @property
    def pages(self) -> dict:
        return {k: v for k, v in (
            (k, self._filter_entry(v))
            for k, v in self._brain.pages.items()
        ) if v is not None}

    @property
    def transitions(self) -> dict:
        return {k: v for k, v in (
            (k, self._filter_entry(v))
            for k, v in self._brain.transitions.items()
        ) if v is not None}

    @property
    def observations(self) -> dict:
        return {k: v for k, v in (
            (k, self._filter_entry(v))
            for k, v in self._brain.observations.items()
        ) if v is not None}

    @property
    def questions(self) -> dict:
        # Questions don't have a clear evidence trail; include all whose
        # related entries exist in the filtered view, plus any standalone.
        out = {}
        page_ids = set(self.pages.keys())
        trans_ids = set(self.transitions.keys())
        obs_ids = set(self.observations.keys())
        valid_refs = page_ids | trans_ids | obs_ids
        for qid, q in self._brain.questions.items():
            if not q.related_entries:
                out[qid] = q
                continue
            if any(r in valid_refs for r in q.related_entries):
                out[qid] = q
        return out

    def run_count(self) -> int:
        return self._snap.evidence_run_count

    def stats(self) -> dict:
        return {
            "snap_id": self._snap.snap_id,
            "upper_bound": self._snap.upper_bound,
            "pages": len(self.pages),
            "transitions": len(self.transitions),
            "observations": len(self.observations),
            "questions": len(self.questions),
            "evidence_run_count": self._snap.evidence_run_count,
        }


__all__ = ["SystemBrain", "BrainView", "FILES"]
