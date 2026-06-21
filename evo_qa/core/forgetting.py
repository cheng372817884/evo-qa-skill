"""
Pseudo-Forgetting — pure logic.

NOTHING in this module touches disk. It takes the current frontmatter
(as a plain dict) plus 'today' and returns:
  - the new state
  - the new retrieval_weight
  - a 'reason' string explaining the transition (or 'no change')

The Curator (curator.py) is responsible for actually applying these
back into files and producing the human-readable brief.

State machine
-------------
   active(1.0) ──60d unused OR fail>30%──> stale(0.4)
   stale       ──60d more   OR fail>50%──> deprecated(0.0)
   deprecated  ──60d not revived────────> archived(-1.0, excluded)
   any         ──explicit the `revive` subcommand────> active (logged in revival_history)

Never-archive guards
--------------------
  - tags ∩ {'critical', 'compliance', 'regulatory', 'golden'} ≠ ∅
  - verified_runs > 20
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional, Iterable


STATE_ACTIVE = "active"
STATE_STALE = "stale"
STATE_DEPRECATED = "deprecated"
STATE_ARCHIVED = "archived"

WEIGHT = {
    STATE_ACTIVE: 1.0,
    STATE_STALE: 0.4,
    STATE_DEPRECATED: 0.0,
    STATE_ARCHIVED: -1.0,
}

NEVER_ARCHIVE_TAGS = {"critical", "compliance", "regulatory", "golden"}
NEVER_ARCHIVE_VERIFIED_THRESHOLD = 20

# Thresholds
STALE_AFTER_DAYS = 60
STALE_FAIL_RATE = 0.30
DEPRECATED_FAIL_RATE = 0.50
ARCHIVED_AFTER_DAYS = 60   # after deprecated, with no revive


@dataclass
class ForgetVerdict:
    new_state: str
    new_weight: float
    reason: str               # human-readable
    transitioned: bool        # True if state changed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(v) -> Optional[date]:
    """Accept date/datetime/'YYYY-MM-DD'/None."""
    if v is None or v == "" or v == "null":
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def _days_between(start: Optional[date], end: date) -> int:
    """Days between two dates. If start is None, returns infinity-ish (9999)."""
    if start is None:
        return 9999
    return (end - start).days


def fail_rate(verified: int, failed: int) -> float:
    total = max(0, verified) + max(0, failed)
    if total <= 0:
        return 0.0
    return float(failed) / float(total)


def is_never_archive(fm: dict) -> bool:
    tags = set(fm.get("tags") or [])
    if tags & NEVER_ARCHIVE_TAGS:
        return True
    try:
        if int(fm.get("verified_runs") or 0) > NEVER_ARCHIVE_VERIFIED_THRESHOLD:
            return True
    except (TypeError, ValueError):
        pass
    return False


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def compute_state(fm: dict, today: Optional[date] = None) -> ForgetVerdict:
    """Decide the entry's new state given its frontmatter today.

    Does NOT mutate fm. Caller writes back if `transitioned=True`.
    """
    today = today or date.today()
    cur_state = fm.get("review_state") or STATE_ACTIVE
    if cur_state not in WEIGHT:
        cur_state = STATE_ACTIVE

    # Read counters
    verified = int(fm.get("verified_runs") or 0)
    failed = int(fm.get("failed_runs") or 0)
    rate = fail_rate(verified, failed)

    last_used = _parse_date(fm.get("last_used_at"))
    last_used_days = _days_between(last_used, today)

    # Honeymoon — newly created entries with no last_used yet.
    # Don't decay them until they've had 60d to be discovered + used.
    created_at = _parse_date(fm.get("created_at"))
    if last_used is None and created_at is not None:
        age_days = _days_between(created_at, today)
        if age_days < STALE_AFTER_DAYS:
            # Treat as "fresh" — bump effective last_used_days down
            last_used_days = age_days

    # decay_history may contain 'archived' transition; honour it
    decayed_to_dep_at = None
    for evt in (fm.get("decay_history") or []):
        if isinstance(evt, dict) and evt.get("to") == STATE_DEPRECATED:
            decayed_to_dep_at = _parse_date(evt.get("at")) or decayed_to_dep_at

    # Never-archive guard short-circuits the worst transitions
    never = is_never_archive(fm)

    # Decide target state — work bottom-up
    target = cur_state

    # archived? Only from deprecated, after 60d not revived
    if cur_state == STATE_ARCHIVED:
        target = STATE_ARCHIVED  # archived is sticky until the `revive` subcommand
    elif cur_state == STATE_DEPRECATED:
        if not never and decayed_to_dep_at and \
           _days_between(decayed_to_dep_at, today) >= ARCHIVED_AFTER_DAYS:
            target = STATE_ARCHIVED
    elif cur_state == STATE_STALE:
        if rate > DEPRECATED_FAIL_RATE or last_used_days >= STALE_AFTER_DAYS * 2:
            # 60d more after stale
            target = STATE_DEPRECATED if not never else STATE_STALE
    else:  # active
        if rate > STALE_FAIL_RATE or last_used_days >= STALE_AFTER_DAYS:
            target = STATE_STALE

    if never and target in (STATE_DEPRECATED, STATE_ARCHIVED):
        # Don't let guarded entries fall past stale
        target = STATE_STALE if cur_state == STATE_ACTIVE else cur_state

    if target == cur_state:
        return ForgetVerdict(
            new_state=cur_state, new_weight=WEIGHT[cur_state],
            reason="no change", transitioned=False,
        )

    # Build reason
    parts = []
    if rate > DEPRECATED_FAIL_RATE:
        parts.append(f"fail_rate={rate:.0%}")
    elif rate > STALE_FAIL_RATE:
        parts.append(f"fail_rate={rate:.0%}")
    if last_used_days >= STALE_AFTER_DAYS:
        if last_used is None:
            parts.append("never used")
        else:
            parts.append(f"unused {last_used_days}d")
    if cur_state == STATE_DEPRECATED and target == STATE_ARCHIVED:
        parts.append("60d in deprecated")
    if never:
        parts.append("never_archive guard floor=stale")
    reason = f"{cur_state} → {target}: " + (", ".join(parts) or "thresholds tripped")

    return ForgetVerdict(
        new_state=target, new_weight=WEIGHT[target],
        reason=reason, transitioned=True,
    )


def revive(fm: dict, *, by: str = "manual",
           note: str = "", today: Optional[date] = None) -> dict:
    """Return a NEW frontmatter dict with state lifted back up + event logged.

    Rules:
      archived  → stale     (gentle re-entry)
      deprecated → active
      stale     → active
      active    → active   (no-op except event)
    """
    today = today or date.today()
    cur = fm.get("review_state") or STATE_ACTIVE
    if cur == STATE_ARCHIVED:
        new = STATE_STALE
    elif cur in (STATE_DEPRECATED, STATE_STALE):
        new = STATE_ACTIVE
    else:
        new = STATE_ACTIVE  # idempotent

    out = dict(fm)
    out["review_state"] = new
    out["retrieval_weight"] = WEIGHT[new]
    out["last_used_at"] = today.isoformat()
    history = list(fm.get("revival_history") or [])
    history.append({
        "at": today.isoformat(),
        "from": cur,
        "to": new,
        "by": by,
        "note": note,
    })
    out["revival_history"] = history
    return out


def apply_state(fm: dict, verdict: ForgetVerdict,
                today: Optional[date] = None) -> dict:
    """Return a NEW frontmatter dict with state + decay event applied.

    Caller writes the file. If verdict.transitioned == False this is a
    near-no-op (just refreshes retrieval_weight).
    """
    today = today or date.today()
    out = dict(fm)
    out["review_state"] = verdict.new_state
    out["retrieval_weight"] = verdict.new_weight
    if verdict.transitioned:
        history = list(fm.get("decay_history") or [])
        history.append({
            "at": today.isoformat(),
            "from": fm.get("review_state") or STATE_ACTIVE,
            "to": verdict.new_state,
            "reason": verdict.reason,
        })
        out["decay_history"] = history
    return out


__all__ = [
    "STATE_ACTIVE", "STATE_STALE", "STATE_DEPRECATED", "STATE_ARCHIVED",
    "WEIGHT", "NEVER_ARCHIVE_TAGS", "STALE_AFTER_DAYS", "STALE_FAIL_RATE",
    "DEPRECATED_FAIL_RATE", "ARCHIVED_AFTER_DAYS",
    "ForgetVerdict", "compute_state", "apply_state", "revive",
    "is_never_archive", "fail_rate",
]
