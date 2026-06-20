"""System brain — mechanical observations from runs.

See SKILL design notes: this is the layer that lets the agent build
a cumulative understanding of the system under test, while staying
honest about what it knows and doesn't know.
"""
from .schemas import (
    Provenance, PageNode, Transition, FieldObservation,
    Question, Contradiction,
)
from .storage import SystemBrain
from .extractor import Extractor, TraceEvent
from .legacy import parse_test_file, GW_ANCHORS
from .digest import render_digest, write_digest

__all__ = [
    "Provenance", "PageNode", "Transition", "FieldObservation",
    "Question", "Contradiction",
    "SystemBrain", "Extractor", "TraceEvent",
    "parse_test_file", "GW_ANCHORS",
    "render_digest", "write_digest",
]
