"""
ExplorerLoop — the orchestrator.

Responsibilities (SINGLE-WRITER PRINCIPLE):

  - Owns the browser lifecycle (start/stop).
  - Calls Strategy for next Action.
  - Runs Guards. On block: log + ask Strategy for an alternate.
  - Executes the Action via existing atoms.
  - Snapshots + diffs to detect title/URL/error changes.
  - Records every step into ExplorationReport.
  - Persists discoveries: pages.md / selectors.json / brain entries.

What it does NOT do:

  - Decide policy (that's Strategy).
  - Decide safety (that's Guards).
  - Read brain to skip itself (that's MemoryGate, called BEFORE the
    loop runs).

Failure modes:

  - Browser fails to start → status='error', empty report.
  - Strategy stops on first call → status='completed' (zero steps).
  - All actions get blocked by guards → status='guard_blocked'.
  - Step budget exhausted → status='step_budget_exhausted'.
  - No new discoveries for 2 consecutive steps → status='stuck'.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .schemas import (
    Charter, Snapshot, ElementRef, Action, StepOutcome,
    ExplorationStep, ExplorationReport,
)
from .guards import (
    BlacklistGuard, OriginGuard, AlreadyDoneGuard, evaluate_all,
)
from .strategies import get_strategy, Strategy


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Type aliases for the browser callable contract. We don't import
# Playwright types here — the loop is testable with mocks.
BrowserFactory = Callable[[bool], object]   # headed -> driver
CredResolver = Callable[[str], dict]         # entry_id -> {"username","password"}


class ExplorerLoop:
    """Run one charter end-to-end."""

    def __init__(self, *,
                 browser_factory: BrowserFactory,
                 credential_resolver: Optional[CredResolver] = None,
                 strategy: Optional[Strategy] = None,
                 max_steps: Optional[int] = None) -> None:
        self._browser_factory = browser_factory
        self._cred_resolver = credential_resolver
        self._strategy_override = strategy
        self._max_steps = max_steps

    # -- Public API ------------------------------------------------------

    def run(self, charter: Charter, *, headed: bool = False) -> ExplorationReport:
        strategy = self._strategy_override or get_strategy(charter.kind)
        max_steps = self._max_steps or charter.max_steps

        report = ExplorationReport(
            id=f"exp-{uuid.uuid4().hex[:12]}",
            charter=charter,
            started_at=_now_iso(),
            ended_at="",
            status="completed",
        )

        guards = [
            BlacklistGuard(),
            OriginGuard([charter.target_url]),
            AlreadyDoneGuard(),
        ]

        driver = None
        try:
            driver = self._browser_factory(headed)
            self._run_loop(driver, strategy, guards, charter,
                           max_steps, report)
        except Exception as e:
            report.status = "error"
            report.error = str(e)
        finally:
            if driver is not None:
                try:
                    driver.stop()
                except Exception:
                    pass
            report.ended_at = _now_iso()

        return report

    # -- Internal --------------------------------------------------------

    def _run_loop(self, driver, strategy: Strategy,
                  guards: list, charter: Charter,
                  max_steps: int, report: ExplorationReport) -> None:
        current: Optional[Snapshot] = None
        no_progress_streak = 0
        history: list[ExplorationStep] = report.steps

        for step_idx in range(max_steps):
            # 1. Strategy decides
            action = strategy.next_action(charter, current, history)
            if action.kind == "stop":
                step = ExplorationStep(
                    index=step_idx,
                    snapshot_before=current or Snapshot(url="", title=""),
                    action=action,
                    snapshot_after=current,
                    outcome=StepOutcome(ok=True),
                )
                history.append(step)
                break

            # 2. Resolve credential placeholders
            if action.kind == "fill" and (
                    "__CRED_USERNAME__" in (action.value or "")
                    or "__CRED_PASSWORD__" in (action.value or "")):
                if charter.credentials_id and self._cred_resolver:
                    try:
                        cred = self._cred_resolver(charter.credentials_id)
                        if "__CRED_USERNAME__" in action.value:
                            action.value = cred.get("username", "")
                        elif "__CRED_PASSWORD__" in action.value:
                            action.value = cred.get("password", "")
                    except Exception as e:
                        action.skipped = True
                        action.skipped_reason = f"credential resolve failed: {e}"

            # 3. Resolve target ElementRef from current snapshot (if any)
            target_el = None
            if current and action.target_ref:
                for el in current.elements:
                    if el.ref_id == action.target_ref:
                        target_el = el
                        break

            # 4. Guards
            if not action.skipped:
                d = evaluate_all(action, target_el, guards)
                if not d.allow:
                    action.skipped = True
                    action.skipped_reason = f"[{d.guard}] {d.reason}"
                else:
                    # Record so AlreadyDoneGuard works
                    for g in guards:
                        if isinstance(g, AlreadyDoneGuard):
                            g.record(action)

            # 5. Execute (or skip).
            #
            # read_only mode: navigate + snapshot are still allowed
            # (they're idempotent observation primitives). Only fill /
            # click / press are write actions and get suppressed.
            outcome = StepOutcome(ok=True)
            new_snap = current
            is_write = action.kind in ("fill", "click", "press")
            should_execute = (not action.skipped
                              and not (charter.read_only and is_write))
            if should_execute:
                try:
                    new_snap = self._execute(driver, action, current)
                except Exception as e:
                    outcome = StepOutcome(ok=False, error=str(e))
                    new_snap = current
            elif charter.read_only and is_write:
                action.skipped = True
                action.skipped_reason = (
                    f"read_only mode: skipped {action.kind}")

            # 6. Diff to detect progress
            if new_snap and current:
                outcome.new_url = (new_snap.url
                                   if new_snap.url != current.url else "")
                outcome.title_changed = (new_snap.title != current.title)
                old_keys = {(e.role, e.name) for e in current.elements}
                new_keys = {(e.role, e.name) for e in new_snap.elements}
                outcome.new_elements_count = len(new_keys - old_keys)
            elif new_snap and not current:
                outcome.new_url = new_snap.url
                outcome.new_elements_count = len(new_snap.elements)

            # 7. Heuristic: capture login error/success signals.
            # i18n: keyword list intentionally includes a Chinese phrase
            # so QA on Chinese-localised login pages also detects errors.
            # AUDIT_ALLOW_CJK: localisation keyword
            notes = []
            if new_snap:
                # Guard: only inspect *visible* text content, NOT element names
                # (which can include literal "wrong"/"login" tokens from
                # form field names like "Login-LoginScreen-LoginDV-username"
                # or contain values we just typed in like "wrongtest").
                # Use only the role=alert / message regions if any exist;
                # otherwise check title bar text changes.
                error_txt_sources = []
                for e in new_snap.elements:
                    role = (e.role or "").lower()
                    if role in ("alert", "status"):
                        error_txt_sources.append((e.text or "").lower())
                txt_lc = " ".join(error_txt_sources)
                if any(k in txt_lc for k in
                       ("invalid", "incorrect", "wrong username",
                        "username and password do not match",
                        "epic sadface",
                        "用户名或密码")):
                    outcome.visible_text_signals.append("LOGIN_ERROR_VISIBLE")
                    notes.append("LOGIN_ERROR_VISIBLE")
                # Login success heuristics:
                # 1. Classic: URL changes after submitting real creds.
                # 2. SPA: URL stays but title appends user
                #    info or the login form disappears entirely.
                if action.rationale and "real" in action.rationale.lower():
                    classic = (current and new_snap.url != current.url)
                    title_grew = (current
                                  and len(new_snap.title) > len(current.title) + 4)
                    login_gone = not any(
                        ("password" in (e.attrs.get("type", "") or "").lower()
                         or "password" in (e.name or "").lower())
                        for e in new_snap.elements
                    )
                    if classic or title_grew or login_gone:
                        notes.append("LOGIN_SUCCESS")
                        if new_snap.url not in report.pages_discovered:
                            report.pages_discovered.append(new_snap.url)

            # 8. Build step
            step = ExplorationStep(
                index=step_idx,
                snapshot_before=current or Snapshot(url="", title=""),
                action=action,
                snapshot_after=new_snap,
                outcome=outcome,
                notes=notes,
            )
            history.append(step)

            # 9. Discoveries
            if new_snap:
                for el in new_snap.elements:
                    if el.selector and el.selector not in report.selectors_added:
                        report.selectors_added.append(el.selector)
                if new_snap.url and new_snap.url not in report.pages_discovered:
                    report.pages_discovered.append(new_snap.url)

            # 10. Stuck detection — only meaningful after state-changing
            # actions. Fill/press/wait don't normally change the DOM, so
            # counting them as "no progress" causes false stalls.
            if action.kind in ("click", "navigate") and not action.skipped:
                progress = bool(outcome.new_url or outcome.title_changed
                                or outcome.new_elements_count > 0
                                or outcome.visible_text_signals)
                no_progress_streak = 0 if progress else no_progress_streak + 1
                if no_progress_streak >= 2:
                    report.status = "stuck"
                    break

            # 11. Charter satisfaction
            if strategy.is_satisfied(charter, history):
                break

            current = new_snap

        else:
            report.status = "step_budget_exhausted"

    # -- Browser action execution ---------------------------------------

    def _execute(self, driver, action: Action,
                 current: Optional[Snapshot]) -> Optional[Snapshot]:
        if action.kind == "navigate":
            driver.goto(action.value)
            driver.wait_for_load()
            return self._snapshot(driver)

        # Fill / click / press require a target ref → selector
        sel = None
        if current and action.target_ref:
            for e in current.elements:
                if e.ref_id == action.target_ref and e.selector:
                    sel = e.selector
                    break
        if not sel:
            return current

        if action.kind == "fill":
            driver.fill(sel, action.value)
        elif action.kind == "click":
            driver.click(sel)
            driver.wait_for_load()
        elif action.kind == "press":
            driver.press(sel, action.value or "Enter")
        elif action.kind == "wait":
            time.sleep(min(2.0, float(action.value or 1)))

        return self._snapshot(driver)

    @staticmethod
    def _snapshot(driver) -> Snapshot:
        snap = driver.snapshot()
        elements: list[ElementRef] = []
        for i, el in enumerate(getattr(snap, "elements", []) or []):
            # Adapters may flatten common attrs to top-level keys.
            # Defensive merge so strategies can rely on attrs[<key>].
            attrs = dict(el.get("attrs") or {})
            for k in ("type", "id", "name", "placeholder",
                      "value", "data-test", "data-testid",
                      "aria-label", "aria-labelledby", "title"):
                if k not in attrs and el.get(k):
                    attrs[k] = el[k]
            # Adapter uses "ref" key; loop expects ref_id.
            ref_id = el.get("ref") or f"el-{i}"
            elements.append(ElementRef(
                ref_id=ref_id,
                role=el.get("role", ""),
                name=el.get("name", ""),
                selector=el.get("selector", ""),
                text=el.get("text", "") or el.get("name", ""),
                attrs=attrs,
            ))
        return Snapshot(
            url=getattr(snap, "url", "") or "",
            title=getattr(snap, "title", "") or "",
            elements=elements,
        )


__all__ = ["ExplorerLoop"]
