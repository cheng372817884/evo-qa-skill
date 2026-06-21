"""
MemoryGate — decide whether we need to explore.

This is the gate that distinguishes Evo QA from "every-time-from-scratch"
test agents. Before any exploration runs, MemoryGate looks at:

  - selectors.json     (which UI elements have we found before? still active?)
  - pages.md           (which pages have we mapped?)
  - brain/exploration/ (what charters have we explored, when?)
  - runs/              (recent successful runs for this charter type?)

It emits an ExplorationNeed:

  skip=True              → memory is sufficient, jump straight to plan
  scope="partial"        → explore only the listed gaps
  scope="full"           → no usable memory, do a full exploration

Heuristics are intentionally simple at MVP. The interface is the
contract; the formula behind it is replaceable.

Coverage formula (MVP):

  let S = number of "active" (review_state=active, last_used <30d)
          selectors that are RELEVANT to this charter
  let P = number of pages.md entries that match the charter's
          probable target areas
  let R = number of successful runs of this charter in last 30 days
  let A = days since last exploration of this charter

  score = w_s * min(S/S_target, 1.0)
        + w_p * min(P/P_target, 1.0)
        + w_r * min(R/R_target, 1.0)
        + w_a * recency_bonus(A)

with weights summing to 1. Targets per charter kind below.

Decision:
  score >= 0.8 AND last_explored < 30d  →  skip=True, proceed_to=plan
  score >= 0.4                          →  scope=partial (cover gaps)
  otherwise                             →  scope=full

Failure modes we explicitly handle:
  - No brain dir yet      → full exploration
  - Corrupt selectors.json → log, full exploration (never crash plan)
  - Outdated brain (every entry stale or deprecated) → full exploration
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .schemas import Charter, Coverage, ExplorationNeed


# ---- Charter-kind specific signals ----------------------------------------

# Per charter kind: targets + relevant signal patterns to look for in
# selectors.json keys / pages.md headings.
_CHARTER_PROFILES = {
    "login": {
        "selector_target": 4,    # username, password, button, error
        "page_target": 2,        # login page + landing page
        "selector_keywords": ["login", "signin", "sign-in", "username",
                              "password", "user-name", "logout", "auth"],
        "page_keywords": ["login", "signin", "auth", "home", "dashboard",
                          "inventory", "landing"],
    },
    "search": {
        "selector_target": 3,
        "page_target": 2,
        "selector_keywords": ["search", "query", "input", "result"],
        "page_keywords": ["search", "result", "list"],
    },
    "cart": {
        "selector_target": 5,
        "page_target": 3,
        "selector_keywords": ["cart", "add-to-cart", "buy", "checkout",
                              "remove", "quantity", "basket"],
        "page_keywords": ["cart", "checkout", "product", "inventory"],
    },
    "form": {
        "selector_target": 4,
        "page_target": 1,
        "selector_keywords": ["submit", "save", "input", "field"],
        "page_keywords": ["form", "edit", "create", "new"],
    },
    "nav": {
        "selector_target": 3,
        "page_target": 3,
        "selector_keywords": ["nav", "menu", "link"],
        "page_keywords": [],  # any page contributes
    },
    "generic": {
        "selector_target": 3,
        "page_target": 2,
        "selector_keywords": [],  # any selector counts toward score
        "page_keywords": [],
    },
}

# Recent-run window
_RECENT_DAYS = 30
_STALE_DAYS = 60


def _parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _days_since(iso: str, now: Optional[datetime] = None) -> Optional[int]:
    dt = _parse_iso(iso)
    if not dt:
        return None
    n = now or datetime.now(timezone.utc)
    delta = n - dt
    return max(0, delta.days)


def _matches_any(haystack: str, keywords: list[str]) -> bool:
    if not keywords:
        return True   # no filter — everything matches
    h = haystack.lower()
    return any(k in h for k in keywords)


# ---------------------------------------------------------------------------
# MemoryGate
# ---------------------------------------------------------------------------

class MemoryGate:
    """Read brain & decide whether exploration is needed.

    Caller passes a Workspace-like object exposing:
      - selectors_path: Path
      - pages_path:     Path
      - brain_dir:      Path (we look at brain/exploration/*.md)
      - runs_iter():    optional — yield run records for this project
                                    (we degrade gracefully if absent)
    """

    def __init__(self, workspace) -> None:
        self.ws = workspace

    # -- Public entry point ---------------------------------------------

    def assess(self, charter: Charter,
               now: Optional[datetime] = None) -> ExplorationNeed:
        try:
            cov = self._compute_coverage(charter, now=now)
        except Exception as e:
            # Defense in depth: never block the user because brain is messy.
            return ExplorationNeed(
                skip=False, scope="full",
                reason=f"Could not read brain ({e}). Doing full exploration.",
                proceed_to="explore",
                coverage=Coverage(score=0.0, notes=[f"error: {e}"]),
            )

        return self._decide(charter, cov)

    # -- Coverage --------------------------------------------------------

    def _compute_coverage(self, charter: Charter,
                          now: Optional[datetime]) -> Coverage:
        profile = _CHARTER_PROFILES.get(charter.kind,
                                        _CHARTER_PROFILES["generic"])
        kw_sel = profile["selector_keywords"]
        kw_pg = profile["page_keywords"]
        target_s = profile["selector_target"]
        target_p = profile["page_target"]

        cov = Coverage()

        # Selectors
        s_path = getattr(self.ws, "selectors_path", None)
        if s_path and Path(s_path).exists():
            try:
                data = json.loads(Path(s_path).read_text(encoding="utf-8"))
                sels = data.get("selectors", {}) or {}
                for key, meta in sels.items():
                    if not _matches_any(key, kw_sel):
                        continue
                    # MVP: treat any selector with a positive score as active.
                    score = float(meta.get("score", 1.0))
                    if score <= 0:
                        continue
                    # Optional staleness check
                    last = meta.get("last_used") or meta.get("first_seen")
                    age = _days_since(last, now=now) if last else None
                    if age is not None and age > _STALE_DAYS:
                        continue
                    cov.selector_hits += 1
            except Exception as e:
                cov.notes.append(f"selectors.json unreadable: {e}")
        cov.selector_total = target_s

        # Pages
        p_path = getattr(self.ws, "pages_path", None)
        if p_path and Path(p_path).exists():
            try:
                text = Path(p_path).read_text(encoding="utf-8")
                # Count h2 headings whose label looks relevant.
                headings = re.findall(r"^##\s+(.+)$", text, re.MULTILINE)
                cov.page_hits = sum(1 for h in headings
                                    if _matches_any(h, kw_pg))
            except Exception as e:
                cov.notes.append(f"pages.md unreadable: {e}")

        # Past explorations
        explore_dir = Path(getattr(self.ws, "brain_dir", "")) / "exploration"
        if explore_dir.exists():
            ages = []
            for f in explore_dir.glob("*.md"):
                # MVP: filename or first-line metadata may carry charter kind
                try:
                    head = f.read_text(encoding="utf-8")[:400]
                except Exception:
                    continue
                if charter.kind in head.lower() or charter.kind == "generic":
                    # Use file mtime as a proxy
                    try:
                        mtime = datetime.fromtimestamp(
                            f.stat().st_mtime, tz=timezone.utc)
                        days = (datetime.now(timezone.utc) - mtime).days
                        ages.append(days)
                    except Exception:
                        pass
            if ages:
                cov.last_explored_days = min(ages)

        # Recent runs (best-effort)
        runs_iter = getattr(self.ws, "runs_iter", None)
        if callable(runs_iter):
            try:
                cov.successful_runs_recent = sum(
                    1 for r in runs_iter()
                    if r.get("status") == "pass"
                    and _days_since(r.get("started_at", ""), now=now)
                        is not None
                    and _days_since(r.get("started_at", ""), now=now)
                        <= _RECENT_DAYS
                    and charter.kind in (r.get("intent", "")
                                         + r.get("charter", "")).lower()
                )
            except Exception as e:
                cov.notes.append(f"runs_iter failed: {e}")

        # Score
        w_s, w_p, w_r, w_a = 0.45, 0.25, 0.15, 0.15
        s_part = min(cov.selector_hits / max(1, target_s), 1.0)
        p_part = min(cov.page_hits / max(1, target_p), 1.0)
        r_part = min(cov.successful_runs_recent / 3.0, 1.0)

        # Recency bonus: full credit if explored <= 7d ago, decays linearly to
        # 0 at 60d.
        if cov.last_explored_days is None:
            a_part = 0.0
        elif cov.last_explored_days <= 7:
            a_part = 1.0
        elif cov.last_explored_days >= 60:
            a_part = 0.0
        else:
            a_part = 1.0 - (cov.last_explored_days - 7) / (60 - 7)

        cov.score = round(w_s * s_part + w_p * p_part
                          + w_r * r_part + w_a * a_part, 3)

        # Identify gaps for partial exploration
        if s_part < 0.6:
            cov.gaps.append("selectors")
        if p_part < 0.6:
            cov.gaps.append("pages")
        if cov.last_explored_days is None or cov.last_explored_days > 30:
            cov.gaps.append("recent_exploration")

        return cov

    # -- Decision --------------------------------------------------------

    def _decide(self, charter: Charter, cov: Coverage) -> ExplorationNeed:
        if cov.score >= 0.8 and (cov.last_explored_days is not None
                                 and cov.last_explored_days <= 30):
            return ExplorationNeed(
                skip=True, scope="none",
                coverage=cov,
                reason=(f"Memory covers '{charter.kind}' "
                        f"(score={cov.score}, "
                        f"last explored {cov.last_explored_days}d ago, "
                        f"{cov.selector_hits}/{cov.selector_total} "
                        f"selectors, {cov.page_hits} pages)."),
                proceed_to="plan",
            )
        if cov.score >= 0.4:
            return ExplorationNeed(
                skip=False, scope="partial",
                cover_what=cov.gaps,
                coverage=cov,
                reason=(f"Memory partially covers '{charter.kind}' "
                        f"(score={cov.score}). Gaps: {cov.gaps}."),
                proceed_to="explore",
            )
        return ExplorationNeed(
            skip=False, scope="full",
            coverage=cov,
            reason=(f"Memory insufficient for '{charter.kind}' "
                    f"(score={cov.score}). Full exploration."),
            proceed_to="explore",
        )


__all__ = ["MemoryGate"]
