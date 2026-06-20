"""
Sink base contract.

A Sink is a per-event reactive consumer on the RunBus.

Contract (every concrete sink MUST honor):

  1. IDEMPOTENT: handle(event) called twice with the same event must
     produce the same end state. The bus may redeliver on crash/replay.

  2. FAST: a single handle() call should complete in well under 60s.
     If you need slow work, you're a Job (see core/scheduler/), not a
     Sink.

  3. SELF-CONTAINED FAILURE: raising from handle() sends the event to
     dead-letter. Don't try to recover globally; just raise. The runner
     will isolate you from other sinks.

  4. NO MAIN-FLOW DEPENDENCIES: a sink may NEVER write to anything the
     main flow reads (e.g., the run record file). Sinks only write to
     reverse-feedback artifacts (brain, knowledge, etc.).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SinkRetryable(Exception):
    """Transient failure: do NOT advance the cursor; retry next tick."""


class Sink(ABC):
    """Override handle(). Set name = unique identifier."""

    name: str = "unnamed"
    accepts: tuple[str, ...] = ()  # event types accepted; empty = all

    @abstractmethod
    def handle(self, event: dict[str, Any]) -> None:
        """Process a single event. Idempotent. Raise on failure."""

    def matches(self, event: dict[str, Any]) -> bool:
        if not self.accepts:
            return True
        return event.get("type") in self.accepts


__all__ = ["Sink", "SinkRetryable"]
