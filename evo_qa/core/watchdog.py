"""
Watchdog — wall-clock enforcement.

Two modes available:

1. **soft (default, used with sync Playwright)** — does NOT spawn a thread
   per atom (sync Playwright cannot be safely called from a worker thread
   because it relies on a greenlet event-loop bound to the calling
   thread). Instead it relies on the executor honouring `atom.options.
   timeout_ms` (or the executor-level default timeout). The wrapper just
   stamps the wall time and, if the call returns success but exceeded
   the policy timeout, records that as advisory (`extra.exceeded_budget=True`).

2. **threaded** — wraps the executor call in a worker thread and joins
   with timeout. Use this only with thread-safe executors (e.g. a fake
   in-memory executor for unit tests, or async Playwright with its own
   loop). On timeout, the worker is abandoned and a synthetic timeout
   AtomResult is returned.

In addition, the **total-run watchdog** is a background thread that
sets a `tripped` flag once the run wall-clock exceeds the budget. The
orchestrator polls this flag between atoms and aborts.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .atoms import Atom, AtomResult, AtomExecutor, ExecutionContext


# ---------------------------------------------------------------------------
# Per-step watchdog wrapper
# ---------------------------------------------------------------------------

def make_step_watchdog(executor: AtomExecutor, default_timeout_s: int,
                       evidence_dir: str,
                       mode: str = "soft") -> Callable[[Atom, ExecutionContext], AtomResult]:
    """Return a callable that wraps `executor.run` with a soft or threaded timeout.

    Parameters
    ----------
    mode : 'soft' | 'threaded'
        - 'soft'     — call directly, rely on executor's own timeout.
                       Safe for sync Playwright. Marks late returns as advisory.
        - 'threaded' — call from a worker thread; abandon on timeout.
                       Only safe for thread-safe executors.
    """
    if mode not in ("soft", "threaded"):
        raise ValueError(f"watchdog mode must be 'soft' or 'threaded', got {mode!r}")

    def call_soft(atom: Atom, ctx: ExecutionContext) -> AtomResult:
        atom_timeout_ms = atom.options.get("timeout_ms", 0)
        budget_s = (atom_timeout_ms / 1000.0) if atom_timeout_ms else default_timeout_s
        start = time.monotonic()
        try:
            r = executor.run(atom, ctx)
        except Exception as e:
            return AtomResult(
                ok=False, error_kind="unknown",
                error_msg=f"{type(e).__name__}: {e}"[:500],
                wall_ms=int((time.monotonic() - start) * 1000),
            )
        wall_ms = int((time.monotonic() - start) * 1000)
        if not r.wall_ms:
            r.wall_ms = wall_ms
        # advisory only — flag if the executor came back late
        if wall_ms > budget_s * 1000:
            r.extra = dict(r.extra or {})
            r.extra["exceeded_budget"] = True
            r.extra["budget_s"] = budget_s
        return r

    def call_threaded(atom: Atom, ctx: ExecutionContext) -> AtomResult:
        atom_timeout_ms = atom.options.get("timeout_ms", 0)
        timeout_s = (atom_timeout_ms / 1000.0) if atom_timeout_ms else default_timeout_s
        result_box: dict = {"r": None, "exc": None}
        start = time.monotonic()

        def worker():
            try:
                result_box["r"] = executor.run(atom, ctx)
            except Exception as e:
                result_box["exc"] = e

        t = threading.Thread(target=worker, name=f"wd-{atom.step_id or atom.name}",
                             daemon=True)
        t.start()
        t.join(timeout=timeout_s)
        wall_ms = int((time.monotonic() - start) * 1000)

        if t.is_alive():
            shot_path = ""
            try:
                shot_path = _emergency_screenshot(executor, ctx, evidence_dir, atom)
            except Exception:
                pass
            return AtomResult(
                ok=False, error_kind="timeout",
                error_msg=f"step exceeded {timeout_s}s wall-clock",
                wall_ms=wall_ms, screenshot_path=shot_path,
                extra={"watchdog": "step", "abandoned_thread": True},
            )

        if result_box["exc"] is not None:
            return AtomResult(
                ok=False, error_kind="unknown",
                error_msg=f"{type(result_box['exc']).__name__}: {result_box['exc']}",
                wall_ms=wall_ms,
            )

        r = result_box["r"]
        if r is None:
            return AtomResult(ok=False, error_kind="unknown",
                              error_msg="executor returned None", wall_ms=wall_ms)
        if not r.wall_ms:
            r.wall_ms = wall_ms
        return r

    return call_soft if mode == "soft" else call_threaded


def _emergency_screenshot(executor: AtomExecutor, ctx: ExecutionContext,
                          evidence_dir: str, atom: Atom) -> str:
    """Attempt a screenshot via adapter hook, ignoring errors."""
    hook = getattr(executor, "emergency_screenshot", None)
    if hook is None:
        return ""
    out = Path(evidence_dir) / f"timeout-{atom.step_id or atom.name}.png"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        hook(ctx, str(out))
        return str(out) if out.exists() else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Total-run watchdog
# ---------------------------------------------------------------------------

@dataclass
class TotalRunWatchdog:
    timeout_s: int
    started_at: float = field(default_factory=time.monotonic)
    _tripped: bool = False
    _stopped: bool = False
    _thread: Optional[threading.Thread] = None

    def start(self) -> None:
        def waiter():
            while not self._stopped:
                if time.monotonic() - self.started_at >= self.timeout_s:
                    self._tripped = True
                    return
                time.sleep(0.5)

        self._thread = threading.Thread(target=waiter, name="wd-total",
                                        daemon=True)
        self._thread.start()

    def tripped(self) -> bool:
        return self._tripped

    def remaining_s(self) -> float:
        return max(0.0, self.timeout_s - (time.monotonic() - self.started_at))

    def stop(self) -> None:
        self._stopped = True


__all__ = ["make_step_watchdog", "TotalRunWatchdog"]
