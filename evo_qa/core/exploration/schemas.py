"""
Exploration schemas.

These are the data structures that flow through the ExplorerLoop:

  Charter        — what the user asked us to explore ("login flow", "search")
  Snapshot       — a frozen view of the page (URL, a11y tree, elements)
  Action         — one decided next step (click, fill, navigate, stop)
  ExplorationStep — a snapshot + action + outcome triple
  ExplorationReport — the full run, persisted to brain/exploration/<id>.md
  ExplorationNeed — MemoryGate's verdict: skip / partial / full
  Coverage        — the input to that verdict

Everything is plain dataclasses. No DB, no ORM. Persisted as YAML
front-matter + Markdown body via brain layer's atomic_write.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional, Literal


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Input / configuration
# ---------------------------------------------------------------------------

@dataclass
class Charter:
    """What the user asked us to explore.

    `kind` drives strategy selection. We start with a small enum and
    fall back to "generic" for anything not yet covered.
    """
    raw: str                       # "test login with valid creds"
    kind: str = "generic"          # login | search | cart | form | nav | generic
    target_url: str = ""
    project: str = ""
    credentials_id: Optional[str] = None  # which entry in the creds store
    max_steps: int = 8
    read_only: bool = False        # if True: only hover/snapshot, no click/fill


# ---------------------------------------------------------------------------
# Live data (snapshots + actions)
# ---------------------------------------------------------------------------

@dataclass
class ElementRef:
    """A reference to a DOM element from the a11y snapshot.

    `selector` is the stable bit (used for codegen + selectors.json).
    `ref_id` is a snapshot-local handle the loop uses to act on it.
    """
    ref_id: str
    role: str
    name: str
    selector: str = ""
    text: str = ""
    attrs: dict = field(default_factory=dict)


@dataclass
class Snapshot:
    """One frozen view of the page."""
    url: str
    title: str
    elements: list[ElementRef] = field(default_factory=list)
    captured_at: str = field(default_factory=_now_iso)

    def find_first(self, *, role: Optional[str] = None,
                   name_contains: Optional[str] = None,
                   attrs_match: Optional[dict] = None) -> Optional[ElementRef]:
        for e in self.elements:
            if role and e.role != role:
                continue
            if name_contains and name_contains.lower() not in (e.name or "").lower():
                continue
            if attrs_match:
                ok = True
                for k, v in attrs_match.items():
                    if e.attrs.get(k) != v:
                        ok = False
                        break
                if not ok:
                    continue
            return e
        return None


@dataclass
class Action:
    """One decided next step."""
    kind: Literal["click", "fill", "press", "navigate", "wait", "stop"]
    target_ref: Optional[str] = None       # references Snapshot.ElementRef.ref_id
    value: str = ""                         # for fill / press
    rationale: str = ""                     # why the decider chose this
    expected: str = ""                      # what we expect to see after
    skipped: bool = False                   # if guards said no
    skipped_reason: str = ""


@dataclass
class StepOutcome:
    """What happened after we executed the action."""
    ok: bool = True
    error: str = ""
    new_url: str = ""
    title_changed: bool = False
    new_elements_count: int = 0
    visible_text_signals: list[str] = field(default_factory=list)
    # ↑ short text snippets we noticed (e.g. "Invalid credentials")


@dataclass
class ExplorationStep:
    """One full step: I saw X, decided Y, did Y, observed Z."""
    index: int
    snapshot_before: Snapshot
    action: Action
    snapshot_after: Optional[Snapshot] = None
    outcome: StepOutcome = field(default_factory=StepOutcome)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

@dataclass
class ExplorationReport:
    """Full record of one ExplorerLoop run."""
    id: str
    charter: Charter
    started_at: str
    ended_at: str
    status: Literal["completed", "step_budget_exhausted",
                    "stuck", "guard_blocked", "error"]
    steps: list[ExplorationStep] = field(default_factory=list)

    # Discoveries — what we want the rest of the system to know about
    pages_discovered: list[str] = field(default_factory=list)         # URLs
    selectors_added: list[str] = field(default_factory=list)          # selector strings
    business_signals: list[str] = field(default_factory=list)
    # ↑ free-form notes ("login error message: 'Invalid credentials'",
    #   "logout button only on /inventory")
    known_unknowns: list[str] = field(default_factory=list)

    error: str = ""


# ---------------------------------------------------------------------------
# Memory gate
# ---------------------------------------------------------------------------

@dataclass
class Coverage:
    """How well does existing brain memory cover this charter?"""
    selector_hits: int = 0          # selectors related to charter, still active
    selector_total: int = 0         # selectors needed (rough estimate)
    page_hits: int = 0              # pages relevant to charter
    successful_runs_recent: int = 0 # runs in last 30d for this charter type
    last_explored_days: Optional[int] = None  # days since last exploration
    last_run_age_days: Optional[int] = None
    score: float = 0.0              # 0..1
    gaps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ExplorationNeed:
    """MemoryGate's verdict.

    `skip=True` means: don't explore, jump straight to plan.
    `scope='partial'` means: explore only the listed gaps.
    `scope='full'`    means: explore everything.
    """
    skip: bool
    scope: Literal["full", "partial", "none"] = "none"
    cover_what: list[str] = field(default_factory=list)
    coverage: Optional[Coverage] = None
    reason: str = ""
    proceed_to: str = ""   # "plan" | "explore"

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


__all__ = [
    "Charter", "ElementRef", "Snapshot", "Action", "StepOutcome",
    "ExplorationStep", "ExplorationReport",
    "Coverage", "ExplorationNeed",
]
