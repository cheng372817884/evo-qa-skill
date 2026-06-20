"""
L1 Data Schemas — the core data contracts for Evo QA.

These dataclasses are contracts: every adapter depends on them, and they
depend on no adapter. Modify with care — breaking backward compatibility
forces every adapter to be rewritten.

See references/VISION.md for the layering rationale.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Optional


# =====================
# Knowledge — a single knowledge entry
# =====================

KnowledgeType = Literal[
    "heuristic",   # heuristic method (SFDIPOT, etc.)
    "technique",   # testing technique (e.g. boundary values)
    "checklist",   # checklist (WCAG, OWASP, etc.)
    "pattern",     # learned pattern
    "concept",     # business concept
    "insight",     # opinion formed by the agent
    "pitfall",     # known trap learned the hard way
    "reference",   # external reference
]

KnowledgeScope = Literal["industry", "project", "session"]
ReviewState = Literal["active", "archived", "pinned"]


@dataclass
class KnowledgeSource:
    type: Literal["builtin", "ingest", "derived"]  # source kind
    ref: str = ""  # citation: file path / URL / "agent observation @ run-3"


@dataclass
class Knowledge:
    """A single knowledge entry. Knowledge is the smallest unit of experience."""
    id: str                                # globally unique: type-slug
    type: KnowledgeType
    scope: KnowledgeScope
    title: str
    summary: str = ""                      # one-sentence summary
    body: str = ""                         # markdown body
    tags: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=lambda: ["all"])  # all | ecommerce | ...
    priority: Literal["high", "medium", "low"] = "medium"
    source: KnowledgeSource = field(default_factory=lambda: KnowledgeSource("builtin", ""))
    confidence: float = 1.0                # 0-1; the agent's confidence in this entry
    review_state: ReviewState = "active"
    created_at: str = ""                   # ISO 8601
    updated_at: str = ""

    @classmethod
    def now(cls) -> str:
        return datetime.utcnow().isoformat()


# =====================
# Spec — OpenSpec-style specification
# =====================

@dataclass
class Scenario:
    name: str
    given: list[str] = field(default_factory=list)
    when: list[str] = field(default_factory=list)
    then: list[str] = field(default_factory=list)


@dataclass
class Requirement:
    name: str
    statement: str  # "The system SHALL ..."
    scenarios: list[Scenario] = field(default_factory=list)


@dataclass
class Spec:
    domain: str  # auth / checkout / ...
    purpose: str = ""
    requirements: list[Requirement] = field(default_factory=list)


# =====================
# Change — one test task
# =====================

@dataclass
class Task:
    id: str         # "1.1", "1.2"
    text: str
    done: bool = False


@dataclass
class DeltaSpec:
    """OpenSpec-style delta: ADDED / MODIFIED / REMOVED."""
    added: list[Requirement] = field(default_factory=list)
    modified: list[Requirement] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)  # requirement names


@dataclass
class Change:
    id: str          # test-login, test-checkout-coupon
    title: str
    proposal: str    # rationale + scope
    design: str = ""  # how it will be implemented
    tasks: list[Task] = field(default_factory=list)
    delta_specs: dict[str, DeltaSpec] = field(default_factory=dict)  # domain -> delta
    status: Literal["draft", "ready", "running", "done", "archived"] = "draft"
    created_at: str = ""
    runs: list[str] = field(default_factory=list)  # list of run_ids


# =====================
# Run — one execution
# =====================

RunStatus = Literal["pass", "fail", "blocked", "partial"]


@dataclass
class Finding:
    """One test finding (may be a bug, or simply a noteworthy observation)."""
    id: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    category: Literal[
        "functional", "visual", "a11y", "console",
        "ux", "content", "security", "performance"
    ]
    title: str
    url: str = ""
    steps_to_reproduce: list[str] = field(default_factory=list)
    expected: str = ""
    actual: str = ""
    evidence: list[str] = field(default_factory=list)  # screenshot paths
    console_errors: list[str] = field(default_factory=list)


@dataclass
class Run:
    id: str
    change_id: str
    started_at: str
    ended_at: str = ""
    status: RunStatus = "blocked"
    executor: str = "playwright"          # playwright / playwright_cli / browser_use
    test_path: str = ""                   # path to the generated test script
    trace_path: str = ""
    headed: bool = False
    findings: list[Finding] = field(default_factory=list)
    notes: str = ""


# =====================
# Workspace configuration
# =====================

@dataclass
class WorkspaceConfig:
    name: str
    url: str
    headed_default: bool = False
    industry: str = ""        # ecommerce / fintech / ""
    brains: list[str] = field(default_factory=list)  # referenced industry brains
    accounts: dict[str, Any] = field(default_factory=dict)  # references to keychain entries
    language: Literal["python", "typescript", "auto"] = "auto"
    notes: str = ""


# =====================
# serialization helpers
# =====================

def to_dict(obj: Any) -> dict:
    """Unified serialization — turn a dataclass into a dict."""
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, list):
        return [to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj


__all__ = [
    "Knowledge", "KnowledgeSource", "KnowledgeType", "KnowledgeScope", "ReviewState",
    "Scenario", "Requirement", "Spec", "DeltaSpec",
    "Task", "Change",
    "Finding", "Run", "RunStatus",
    "WorkspaceConfig",
    "to_dict",
]
