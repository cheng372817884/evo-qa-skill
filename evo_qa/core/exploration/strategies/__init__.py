"""
Strategy registry — charter-aware deciders.

Each Strategy plugs into ExplorerLoop and answers ONE question per
step:

    Given the current Snapshot + the history of steps taken so far,
    what is the next Action?

The interface is intentionally tiny. v1.0.4 ships rule-based
strategies (login, generic). v1.0.5 will add an LLMStrategy that
implements the same interface — drop-in replacement.

We never let a strategy touch the browser directly. The loop owns
that. A strategy is pure: (Snapshot, history) -> Action.

Strategies should:

  - Be deterministic (or pseudo-random with a fixed seed).
  - Return Action(kind='stop', rationale=...) when their
    objective is met or they don't know what to do next.
  - Tolerate a None snapshot (very first call, before any nav).
"""
from __future__ import annotations

from typing import Optional, Protocol

from ..schemas import Action, Charter, ExplorationStep, Snapshot


class Strategy(Protocol):
    """Decider interface."""

    name: str

    def initial_action(self, charter: Charter) -> Action:
        """First action — usually navigate to charter.target_url."""
        ...

    def next_action(self, charter: Charter,
                    current: Optional[Snapshot],
                    history: list[ExplorationStep]) -> Action:
        """Decide the next step. Return Action(kind='stop') to finish."""
        ...

    def is_satisfied(self, charter: Charter,
                     history: list[ExplorationStep]) -> bool:
        """Have we accomplished the charter? (used as soft stop signal)"""
        ...


# Registry — populated at import time below
_REGISTRY: dict[str, Strategy] = {}


def register(name: str, strategy: Strategy) -> None:
    _REGISTRY[name] = strategy


def get_strategy(charter_kind: str) -> Strategy:
    if charter_kind in _REGISTRY:
        return _REGISTRY[charter_kind]
    return _REGISTRY["generic"]


def list_strategies() -> list[str]:
    return sorted(_REGISTRY.keys())


# Bootstrap built-in strategies on import. We defer the import to avoid
# circulars.
def _bootstrap() -> None:
    from . import login as _login    # noqa: F401
    from . import generic as _gen    # noqa: F401


_bootstrap()


__all__ = ["Strategy", "register", "get_strategy", "list_strategies"]
