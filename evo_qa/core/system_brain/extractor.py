"""
System brain extractor.

Two paths:

1. v1.0 native — feed it a list of trace events (one per atom), each
   with {atom, target, value, ok, page_title_before, page_title_after,
   url_before, url_after, wall_ms}. We emit page nodes / transitions /
   field observations directly.

2. Reverse-engineering for legacy runs — given a pytest test file +
   run record JSON (no per-atom trace), parse the script, infer atoms,
   then run path 1.

Design rules (keep us honest, prevent over-fitting):

  - Field values seen are RECORDED, not generalised
  - Repeated values raise confidence, novel values widen coverage
  - Question auto-spawn happens only on N >= 3 same-value runs
    ("seen 3+ times — is it required?") — never N=1 false positive
  - Contradictions trigger demotion + question, never silent overwrite
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .schemas import (
    PageNode, Transition, FieldObservation, Question, Contradiction,
    Provenance,
)
from .storage import SystemBrain


@dataclass
class TraceEvent:
    """One observed atom execution."""
    atom: str
    target: str = ""
    value: str = ""
    ok: bool = True
    page_title_before: str = ""
    page_title_after: str = ""
    url_before: str = ""
    url_after: str = ""
    wall_ms: int = 0
    notes: str = ""


# ---- helpers --------------------------------------------------------------

_TITLE_NORMALIZERS = [
    # Strip build noise from page titles
    (re.compile(r"^\[DEV mode[^\]]*\]\s*"), ""),
    (re.compile(r"\(Super User\)"), "(Super User)"),
]


def _normalize_title(t: str) -> str:
    if not t:
        return ""
    out = t.strip()
    for pat, repl in _TITLE_NORMALIZERS:
        out = pat.sub(repl, out)
    return out


def _slug_from_title(t: str) -> str:
    """Best-effort stable slug from a page title.

    'App Name (User Role) Page Title' -> 'page-title'
    'Login' -> 'login'
    """
    n = _normalize_title(t)
    # Heuristic: take the trailing segment after "(...) " if present
    m = re.search(r"\)\s*(.+)$", n)
    tail = m.group(1) if m else n
    tail = tail.strip()
    if not tail:
        return "unknown"
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", tail).strip("-").lower()
    return slug or "unknown"


def _detect_field_kind(atom: str) -> str:
    return {
        "fill": "input",
        "select": "select",
        "select_option_smart": "dropdown",
        "press": "input",
        "click": "button",
    }.get(atom, "unknown")


# ---- main extractor -------------------------------------------------------

class Extractor:
    """Mechanically updates a SystemBrain from a list of TraceEvents."""

    def __init__(self, brain: SystemBrain):
        self.brain = brain
        self.report = {
            "pages": {"new": 0, "reinforced": 0, "revised": 0},
            "transitions": {"new": 0, "reinforced": 0, "revised": 0},
            "observations": {"new": 0, "reinforced": 0, "revised": 0},
            "questions_added": 0,
            "contradictions": 0,
        }

    def ingest(self, events: list[TraceEvent], *,
               run_id: str, build: str = "") -> dict:
        """Process a full run's worth of events. Returns summary dict."""

        # 1) PAGES — every distinct title we see becomes a node
        seen_pages: dict[str, str] = {}    # slug -> normalized title
        for ev in events:
            for raw in (ev.page_title_before, ev.page_title_after):
                if not raw:
                    continue
                norm = _normalize_title(raw)
                slug = _slug_from_title(norm)
                seen_pages.setdefault(slug, norm)

        for slug, title in seen_pages.items():
            node = PageNode(
                id=slug,
                title_pattern=title,
                role="screen",
                description=f"Auto-extracted from run {run_id}",
            )
            kind, _ = self.brain.upsert_page(node, run_id=run_id, build=build)
            self.report["pages"][kind] += 1

        # 2) TRANSITIONS — title changes are edges
        for i, ev in enumerate(events):
            if not ev.ok:
                continue
            t_before = _normalize_title(ev.page_title_before)
            t_after = _normalize_title(ev.page_title_after)
            if not t_before or not t_after or t_before == t_after:
                continue
            from_slug = _slug_from_title(t_before)
            to_slug = _slug_from_title(t_after)
            if from_slug == to_slug:
                continue

            tid = f"{from_slug}->{to_slug}"
            t = Transition(
                id=tid,
                from_page=from_slug,
                to_page=to_slug,
                intent=ev.notes or f"{ev.atom} {ev.target}".strip(),
                trigger_atoms=[{
                    "atom": ev.atom,
                    "target": ev.target[:120],
                    "note": ev.notes[:120] if ev.notes else "",
                }],
                avg_duration_ms=ev.wall_ms,
            )
            kind, _ = self.brain.upsert_transition(t, run_id=run_id, build=build)
            self.report["transitions"][kind] += 1

        # 3) FIELD OBSERVATIONS — fill / select on a target
        # Anchor each field observation to the page it was on, using the
        # page title BEFORE the action (the action happens on that page).
        for ev in events:
            if ev.atom not in ("fill", "select", "select_option_smart"):
                continue
            if not ev.target:
                continue
            page_slug = _slug_from_title(_normalize_title(
                ev.page_title_before or ev.page_title_after))
            obs_id = f"field-{page_slug}-{self._target_slug(ev.target)}"

            obs = FieldObservation(
                id=obs_id,
                page=page_slug,
                selector=ev.target,
                field_kind=_detect_field_kind(ev.atom),
                values_seen=[ev.value] if ev.value else [],
                operations_seen=[ev.atom],
                quirks=self._infer_quirks(ev),
            )
            kind, _ = self.brain.upsert_observation(
                obs, run_id=run_id, build=build)
            self.report["observations"][kind] += 1

        # 4) QUESTIONS — auto-spawn when interesting patterns emerge
        self._spawn_questions(run_id)

        return self.report

    @staticmethod
    def _target_slug(target: str) -> str:
        """Stable per-field slug.

        For GW wrapper-id selectors like:
            '#NewContact-...-Name_Input input'
        we want the *field* identifier ('Name'), not the trailing tag.

        Strategy:
          - Strip everything after a space (e.g. "#x input" -> "#x")
          - If the id ends with '_Input' / '_Container' / '_Wrapper'
            etc., drop that suffix
          - Take the last hyphen-separated segment
        """
        head = target.split()[0] if target else target
        head = head.lstrip("#.").strip()
        # Drop common GW wrapper suffixes
        for suffix in ("_Input", "_Container", "_Wrapper", "_Cell"):
            if head.endswith(suffix):
                head = head[: -len(suffix)]
                break
        # Take last hyphenated segment as the human-meaningful piece
        if "-" in head:
            tail = head.rsplit("-", 1)[-1]
        else:
            tail = head
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", tail).strip("-").lower()
        return slug or "unknown"

    @staticmethod
    def _infer_quirks(ev: TraceEvent) -> list[str]:
        out = []
        if "_Input" in ev.target and " input" in ev.target.lower():
            out.append("gw-wrapper-id-pattern")
        if ev.atom == "press" and ev.value == "Enter":
            out.append("submit-via-enter-key")
        return out

    def _spawn_questions(self, run_id: str) -> None:
        """Auto-derive open questions from current brain state.

        Conservative: only spawn when patterns are strong enough to be
        worth asking about, but vague enough that we honestly don't know
        the answer yet.
        """
        # Q1: Repeatedly-set field values — is the field required?
        for obs in self.brain.observations.values():
            if (len(obs.prov.evidence) >= 3
                    and obs.field_kind in ("input", "select", "dropdown")
                    and len(obs.values_seen) <= 4):
                qid = f"q-required-{obs.id}"
                if qid not in self.brain.questions:
                    self.brain.add_question(Question(
                        id=qid,
                        text=(f"Field '{obs.id}' has been filled in "
                              f"{len(obs.prov.evidence)} runs with "
                              f"{len(obs.values_seen)} distinct values "
                              f"({', '.join(obs.values_seen[:3])}). "
                              f"Is it required? What happens if left empty?"),
                        layer="system",
                        related_entries=[obs.id],
                        suggested_test=(
                            f"Run the same flow with this field empty; "
                            f"observe whether validation rejects it."),
                    ))
                    self.report["questions_added"] += 1

        # Q2: Singleton transitions (only one path observed) — are there others?
        from_pages: dict[str, list[str]] = {}
        for t in self.brain.transitions.values():
            from_pages.setdefault(t.from_page, []).append(t.id)
        for page, tids in from_pages.items():
            if len(tids) == 1:
                qid = f"q-other-paths-{page}"
                if qid not in self.brain.questions:
                    self.brain.add_question(Question(
                        id=qid,
                        text=(f"Only one transition observed FROM '{page}': "
                              f"{tids[0]}. Are there other paths leaving "
                              f"this page?"),
                        layer="system",
                        related_entries=tids,
                        suggested_test=(
                            f"Explore '{page}' — list all clickable elements "
                            f"and observe where each leads."),
                    ))
                    self.report["questions_added"] += 1

        # Q3: Build version drift detected — could be a UI change
        builds_seen = set()
        for store in (self.brain.pages, self.brain.transitions,
                      self.brain.observations):
            for entry in store.values():
                b = entry.prov.last_verified_build
                if b:
                    builds_seen.add(b)
        if len(builds_seen) > 1:
            qid = "q-build-drift-detected"
            if qid not in self.brain.questions:
                self.brain.add_question(Question(
                    id=qid,
                    text=(f"Multiple build versions observed: "
                          f"{sorted(builds_seen)}. Did the UI change between "
                          f"them? Some brain entries may have silently drifted."),
                    layer="system",
                    suggested_test=(
                        "Re-run a known-good case under the latest build; "
                        "check whether selectors and titles still match."),
                ))
                self.report["questions_added"] += 1


__all__ = ["Extractor", "TraceEvent"]
