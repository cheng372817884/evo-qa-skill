"""
Three-tier retry policy for atom execution.

Tier 1 — physical retries (per atom):
   For transient errors (timeout, navigation, network blip, page closed).
   Up to N attempts with exponential backoff.

Tier 2 — heal (per atom):
   If physical retries are exhausted AND error class looks like selector
   drift, ask the healer for alternate atoms; try the best one once.
   Each heal counts against the run-wide case budget.

Tier 3 — case budget (per run):
   Across the entire test run, only K total "extra attempts" are allowed
   (physical retries + heals combined). Once exhausted, the next failure
   stops the whole run rather than chewing through everything.

A separate Watchdog (see watchdog.py) enforces wall-clock per-step and
per-run timeouts orthogonally.
"""
from __future__ import annotations

import time
import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from .atoms import Atom, AtomResult, AtomExecutor, ExecutionContext


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

# Errors worth a physical retry — usually transient infrastructure blips.
PHYSICAL_TRANSIENT = {
    "timeout",
    "navigation",
    "network",
    "page_closed",
    "disconnected",
}

# Errors that smell like the UI moved — eligible for healer.
SELECTOR_DRIFT = {
    "selector_not_found",
    "element_not_visible",
    "stale_element",
}

# Genuine functional findings — NEVER retried.
FUNCTIONAL = {
    "assertion",
    "expectation",
}


def classify_error(error_kind: str) -> str:
    """Return one of: 'transient' | 'drift' | 'functional' | 'unknown'."""
    k = (error_kind or "").lower()
    if k in PHYSICAL_TRANSIENT:
        return "transient"
    if k in SELECTOR_DRIFT:
        return "drift"
    if k in FUNCTIONAL:
        return "functional"
    return "unknown"


# ---------------------------------------------------------------------------
# Policy + stats
# ---------------------------------------------------------------------------

@dataclass
class RetryPolicy:
    physical_retries: int = 3       # per atom
    heal_retries: int = 1           # per atom
    case_budget: int = 10           # per run, shared
    per_step_timeout_s: int = 30
    total_run_timeout_s: int = 600
    backoff_base_s: float = 0.5
    backoff_factor: float = 2.0
    backoff_jitter: float = 0.2     # ±20% jitter on each backoff


@dataclass
class RetryStats:
    physical_attempts: int = 0      # total across run
    heals_attempted: int = 0
    heals_succeeded: int = 0
    case_budget_used: int = 0
    case_budget_exhausted: bool = False
    per_step: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Healer protocol
# ---------------------------------------------------------------------------

class Healer:
    """Default healer — proposes nothing. Overridden by adapters."""

    def propose(self, atom: Atom, last_result: AtomResult,
                ctx: ExecutionContext) -> list[Atom]:
        return []


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

@dataclass
class StepOutcome:
    atom: Atom
    final_result: AtomResult
    attempts: int = 0          # total physical attempts
    heals: int = 0             # heal cycles used
    healed_with: Optional[Atom] = None   # the successful alternate, if any
    history: list[AtomResult] = field(default_factory=list)


class RetryDriver:
    """Drives a single atom through the three-tier policy.

    The orchestrator wraps every atom call via this driver.
    The executor is dumb — it just does one attempt.
    """

    def __init__(self, executor: AtomExecutor, policy: RetryPolicy,
                 stats: RetryStats, healer: Optional[Healer] = None,
                 watchdog_call: Optional[Callable] = None):
        self.executor = executor
        self.policy = policy
        self.stats = stats
        self.healer = healer or Healer()
        # watchdog_call is a callable wrapping executor.run with a timeout.
        # Falls back to executor.run if no watchdog supplied.
        self._call = watchdog_call or (lambda atom, ctx: self.executor.run(atom, ctx))

    # -- helpers ----------------------------------------------------------

    def _backoff(self, attempt: int) -> None:
        base = self.policy.backoff_base_s * (self.policy.backoff_factor ** attempt)
        jitter = base * self.policy.backoff_jitter
        time.sleep(max(0.0, base + random.uniform(-jitter, jitter)))

    def _budget_left(self) -> int:
        return max(0, self.policy.case_budget - self.stats.case_budget_used)

    def _consume_budget(self, n: int = 1) -> bool:
        if self._budget_left() < n:
            self.stats.case_budget_exhausted = True
            return False
        self.stats.case_budget_used += n
        return True

    # -- main entry -------------------------------------------------------

    def run_atom(self, atom: Atom, ctx: ExecutionContext) -> StepOutcome:
        outcome = StepOutcome(atom=atom, final_result=AtomResult(ok=False))
        last: Optional[AtomResult] = None

        # Tier 1 — physical retries
        for attempt in range(self.policy.physical_retries):
            outcome.attempts += 1
            self.stats.physical_attempts += 1
            r = self._call(atom, ctx)
            outcome.history.append(r)
            last = r
            if r.ok:
                outcome.final_result = r
                self._record_step(outcome)
                return outcome

            cls = classify_error(r.error_kind)
            if cls != "transient":
                # Don't waste retries on drift / functional / unknown
                break
            if attempt < self.policy.physical_retries - 1:
                if not self._consume_budget(1):
                    break
                self._backoff(attempt)

        # Tier 2 — heal (only if drift)
        cls = classify_error(last.error_kind if last else "")
        if cls == "drift" and self.policy.heal_retries > 0:
            for heal_attempt in range(self.policy.heal_retries):
                if not self._consume_budget(1):
                    break
                outcome.heals += 1
                self.stats.heals_attempted += 1
                alternates = self.healer.propose(atom, last, ctx)
                if not alternates:
                    break
                # Try only the first proposal (best-ranked)
                alt = alternates[0]
                r = self._call(alt, ctx)
                outcome.history.append(r)
                last = r
                if r.ok:
                    self.stats.heals_succeeded += 1
                    outcome.healed_with = alt
                    outcome.final_result = r
                    self._record_step(outcome)
                    return outcome

        outcome.final_result = last or AtomResult(
            ok=False, error_kind="unknown", error_msg="no attempts made"
        )
        self._record_step(outcome)
        return outcome

    # -- bookkeeping ------------------------------------------------------

    def _record_step(self, outcome: StepOutcome) -> None:
        self.stats.per_step.append({
            "step_id": outcome.atom.step_id,
            "atom": outcome.atom.name,
            "ok": outcome.final_result.ok,
            "attempts": outcome.attempts,
            "heals": outcome.heals,
            "healed_with": (outcome.healed_with.name
                            if outcome.healed_with else None),
            "error_kind": outcome.final_result.error_kind,
            "wall_ms": outcome.final_result.wall_ms,
        })


__all__ = [
    "RetryPolicy", "RetryStats", "RetryDriver", "StepOutcome",
    "Healer", "classify_error",
    "PHYSICAL_TRANSIENT", "SELECTOR_DRIFT", "FUNCTIONAL",
]
