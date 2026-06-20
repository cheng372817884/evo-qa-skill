"""
core.exploration — sniff before you write.

Public API:

    from evo_qa.core.exploration import (
        Charter, ExplorationReport, ExplorationNeed,
        MemoryGate, ExplorerLoop, render_report,
    )

Design rationale: see `references/exploration-design.zh.md` (Chinese,
authoritative) and the inline docstrings in each submodule.
"""
from __future__ import annotations

from .schemas import (
    Charter, Snapshot, ElementRef, Action,
    StepOutcome, ExplorationStep, ExplorationReport,
    Coverage, ExplorationNeed,
)
from .memory_gate import MemoryGate
from .loop import ExplorerLoop
from .report import render as render_report, write as write_report
from .strategies import get_strategy, list_strategies, register

__all__ = [
    # Schemas
    "Charter", "Snapshot", "ElementRef", "Action",
    "StepOutcome", "ExplorationStep", "ExplorationReport",
    "Coverage", "ExplorationNeed",
    # Components
    "MemoryGate", "ExplorerLoop",
    "render_report", "write_report",
    # Strategy registry
    "get_strategy", "list_strategies", "register",
]
