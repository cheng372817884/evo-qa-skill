"""
Generic fallback strategy.

When a charter doesn't match any specialised strategy, we do a
shallow breadth-first probe: open the target URL, snapshot, then
stop.

This is intentionally minimal at MVP. It exists so the framework
always has SOMETHING to return; it's not a real exploration.

When v1.0.5 introduces an LLMStrategy, this file becomes obsolete
for non-trivial charters — but we keep it as a no-LLM-available
fallback.
"""
from __future__ import annotations

from typing import Optional

from ..schemas import Action, Charter, ExplorationStep, Snapshot
from . import register


class GenericStrategy:
    name = "generic"

    def initial_action(self, charter: Charter) -> Action:
        return Action(
            kind="navigate",
            value=charter.target_url,
            rationale="Generic probe: open the target URL.",
            expected="The application's landing page.",
        )

    def is_satisfied(self, charter: Charter,
                     history: list[ExplorationStep]) -> bool:
        # We "succeed" as soon as we have one snapshot.
        return any(s.snapshot_after is not None for s in history)

    def next_action(self, charter: Charter,
                    current: Optional[Snapshot],
                    history: list[ExplorationStep]) -> Action:
        if current is None:
            return self.initial_action(charter)
        return Action(
            kind="stop",
            rationale="Generic strategy stops after one snapshot. "
                      "Specialised strategies (login/search/cart) or "
                      "the v1.0.5 LLM strategy will go deeper.",
        )


register("generic", GenericStrategy())
