"""
System brain schemas.

Each entry carries the SAME provenance metadata so we can be honest
about what we know and what we don't. This is intentional: it's the
counter-measure against "experience-based bias" that the user explicitly
asked us to bake in.

Layers:
  - System brain  (this file)  — mechanical observations from runs
  - Business brain (Phase 2)   — reflective summaries (LLM-assisted)

A schema entry is NEVER overwritten. Updates create a revision_history
event and may move confidence up/down.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Literal


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@dataclass
class Provenance:
    """Common metadata every brain entry carries.

    Designed so that humans/LLMs reading the brain can immediately answer:
      - Where did this come from?         (evidence)
      - How sure are we?                  (confidence)
      - What would prove me wrong?        (would_be_falsified_by)
      - What didn't I check?              (known_unknowns)
      - When does this expire?            (decay_when, last_verified_at)
      - Has this been challenged?         (contradictions)
    """
    confidence: float = 0.5                     # 0.0 - 1.0
    evidence: list[str] = field(default_factory=list)   # run IDs

    would_be_falsified_by: list[str] = field(default_factory=list)
    known_unknowns: list[str] = field(default_factory=list)
    contradicts: list[str] = field(default_factory=list)  # contradiction IDs

    first_seen_run: str = ""
    last_verified_run: str = ""
    first_seen_build: str = ""
    last_verified_build: str = ""
    decay_when: list[str] = field(default_factory=list)

    revision_history: list[dict] = field(default_factory=list)

    review_state: Literal["active", "stale", "deprecated", "archived"] = "active"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def reinforce(self, run_id: str, build: str = "") -> None:
        """Another run confirmed this entry."""
        if run_id not in self.evidence:
            self.evidence.append(run_id)
        self.last_verified_run = run_id
        if build:
            self.last_verified_build = build
        # Confirmations slowly raise confidence (asymptote at 0.95)
        self.confidence = min(0.95, self.confidence + (1 - self.confidence) * 0.2)
        self.updated_at = _now()
        self.review_state = "active"

    def revise(self, *, from_value, to_value, reason: str, run_id: str) -> None:
        """Something changed about this entry — record honestly."""
        self.revision_history.append({
            "at": _now(),
            "run_id": run_id,
            "from": from_value,
            "to": to_value,
            "reason": reason,
        })
        # A revision (especially due to contradiction) drops confidence
        self.confidence = max(0.1, self.confidence - 0.3)
        self.updated_at = _now()


# --- L1 Pages ---------------------------------------------------------------

@dataclass
class PageNode:
    """A page (or screen) the agent has observed."""
    id: str                              # stable slug: "summary"
    title_pattern: str                   # observed page.title (may have variants)
    title_aliases: list[str] = field(default_factory=list)
    role: str = "screen"                 # screen | dialog | menu | error
    url_pattern: str = ""                # mostly empty for SPAs
    key_elements: list[str] = field(default_factory=list)  # selectors that identify this page
    description: str = ""
    prov: Provenance = field(default_factory=Provenance)


# --- L2 Transitions ---------------------------------------------------------

@dataclass
class Transition:
    """An edge between pages, observed during a run."""
    id: str                              # "summary->new_company_form"
    from_page: str
    to_page: str
    intent: str = ""                     # human-readable: "open New Company form"
    trigger_atoms: list[dict] = field(default_factory=list)
    # Each atom kept minimal: {"name": "click", "target": "...", "note": ""}
    avg_duration_ms: int = 0
    prov: Provenance = field(default_factory=Provenance)


# --- L3 Field observations --------------------------------------------------

@dataclass
class FieldObservation:
    """What we've SEEN a field accept — NOT a constraint, NOT a rule.

    Example: state field has been seen with values [Ohio, Arizona, MA, TX].
    That does NOT mean it's an enum, NOT mean those are the only values,
    NOT mean it rejects free text. It means: those four were entered and
    accepted.
    """
    id: str                              # "field-state-on-new-company-form"
    page: str
    selector: str
    field_kind: str = "input"            # input | select | textarea | checkbox | radio
    label_seen: list[str] = field(default_factory=list)
    values_seen: list[str] = field(default_factory=list)
    operations_seen: list[str] = field(default_factory=list)  # ["fill", "select_option"]
    quirks: list[str] = field(default_factory=list)           # observed quirks (e.g. wrapper-id)
    prov: Provenance = field(default_factory=Provenance)


# --- L4 Questions -----------------------------------------------------------

@dataclass
class Question:
    """An explicit known-unknown — drives future exploration.

    Questions are first-class: they're how the brain admits ignorance
    instead of pretending. A question that gets answered creates a new
    observation and the question is archived (not deleted).
    """
    id: str
    text: str                            # "Is address_type required to update?"
    layer: str = "system"                # system | business
    related_entries: list[str] = field(default_factory=list)
    suggested_test: str = ""             # how to verify
    state: Literal["open", "answered", "obsolete"] = "open"
    answer: str = ""
    answered_by_run: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)


# --- L5 Contradictions ------------------------------------------------------

@dataclass
class Contradiction:
    """A run observed something that contradicts existing brain.

    Contradictions are NEVER silent overwrites. They're recorded, the
    relevant entries are demoted to 'stale', and a question is auto-spawned.
    """
    id: str                              # "contra-2026-06-18-state-field-rejected"
    detected_at: str = field(default_factory=_now)
    run_id: str = ""
    affected_entry: str = ""             # id of the entry contradicted
    expected: str = ""
    observed: str = ""
    severity: Literal["info", "warning", "critical"] = "warning"
    spawned_question: str = ""
    resolved: bool = False
    resolution: str = ""


# --- Helpers ---------------------------------------------------------------

def to_yaml_dict(obj) -> dict:
    """Convert dataclass to a YAML-friendly dict (no None scalars)."""
    if hasattr(obj, "__dataclass_fields__"):
        d = asdict(obj)
        return _clean(d)
    return obj


def _clean(d):
    if isinstance(d, dict):
        return {k: _clean(v) for k, v in d.items() if v not in (None, "")}
    if isinstance(d, list):
        return [_clean(x) for x in d]
    return d


__all__ = [
    "Provenance", "PageNode", "Transition", "FieldObservation",
    "Question", "Contradiction", "to_yaml_dict",
]
