"""
Failure attribution — turn raw retry/heal results into a verdict
the human (and the curator) can act on.

Three buckets:

- **system_failure**  — environment issue (network down, login expired,
   page crashed, total-run timeout). Test plan is fine; report and
   record as a `pitfall` candidate so future runs hit it less often.

- **drift**           — UI shape changed (selector not found, role moved).
   Healed or not, signals selectors need refreshing. Surfaces as
   `the `heal` subcommand` suggestion + bumps selector "drift score".

- **exploration_failure** — assertion failed on a real check
   (expect_visible / expect_text / expect_url). Genuine functional
   finding. Surfaces in the report under "Findings".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .retry import StepOutcome, classify_error


@dataclass
class Attribution:
    verdict: str                       # 'pass' | 'system_failure' | 'drift' | 'exploration_failure'
    confidence: float = 1.0
    reasons: list[str] = field(default_factory=list)
    drifted_selectors: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)


SYSTEM_HINTS = {
    "navigation",   # could be auth/cookie/server problem
    "network",
    "page_closed",
    "disconnected",
}


def attribute_run(step_outcomes: Iterable[StepOutcome],
                  total_timeout_tripped: bool = False,
                  case_budget_exhausted: bool = False) -> Attribution:
    """Decide what kind of run this was."""
    outcomes = list(step_outcomes)
    failed = [o for o in outcomes if not o.final_result.ok]

    # Pass — every step succeeded (heals counted as success too).
    if not failed and not total_timeout_tripped:
        return Attribution(verdict="pass", confidence=1.0,
                           reasons=["all steps passed"])

    # Total timeout dominates everything else.
    if total_timeout_tripped:
        return Attribution(
            verdict="system_failure",
            confidence=1.0,
            reasons=["total-run watchdog tripped"],
            failed_steps=[o.atom.step_id for o in failed],
        )

    # Categorise each failure by error class.
    classes: list[str] = []
    drifted: list[str] = []
    asserts: list[str] = []
    for o in failed:
        cls = classify_error(o.final_result.error_kind)
        classes.append(cls)
        if cls == "drift":
            if o.atom.target:
                drifted.append(o.atom.target)
        if cls == "functional":
            asserts.append(o.atom.step_id or o.atom.description)

    reasons: list[str] = []
    if case_budget_exhausted:
        reasons.append("case budget exhausted before completion")

    # Heuristic priority: functional > drift > system > unknown.
    if any(c == "functional" for c in classes):
        return Attribution(
            verdict="exploration_failure",
            confidence=0.95,
            reasons=reasons + [f"{len(asserts)} assertion(s) failed"],
            failed_steps=[o.atom.step_id for o in failed
                          if classify_error(o.final_result.error_kind) == "functional"],
        )

    if any(c == "drift" for c in classes):
        # Some heals may have succeeded — drift is still the verdict
        # for the run because something needed healing.
        return Attribution(
            verdict="drift",
            confidence=0.85,
            reasons=reasons + [f"{len(drifted)} selector(s) drifted"],
            drifted_selectors=drifted,
            failed_steps=[o.atom.step_id for o in failed
                          if classify_error(o.final_result.error_kind) == "drift"],
        )

    # Anything else — system or unknown; group as system.
    return Attribution(
        verdict="system_failure",
        confidence=0.7,
        reasons=reasons + [
            f"{len([c for c in classes if c == 'transient'])} transient, "
            f"{len([c for c in classes if c == 'unknown'])} unknown"
        ],
        failed_steps=[o.atom.step_id for o in failed],
    )


__all__ = ["Attribution", "attribute_run"]
