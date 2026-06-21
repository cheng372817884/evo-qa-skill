"""
Adapter Registry — wires all adapters.

Adding a new adapter only requires changing this one file. The orchestrator
stays untouched.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

from ..adapters.browsers.playwright_adapter import PlaywrightAdapter
from ..adapters.ingestors.markdown import MarkdownIngestor
from ..adapters.ingestors.url import URLIngestor
from ..adapters.reporters.markdown import MarkdownReporter
from ..adapters.retrievers.grep import GrepRetriever
from ..adapters.reviewers.post_turn import PostTurnReviewer
from ..adapters.runners.pytest_runner import PytestRunner
from .interfaces import (
    BrowserAdapter, Ingestor, Reporter, Retriever, Reviewer, Source, TestRunner,
)


def get_ingestors() -> list[Ingestor]:
    return [MarkdownIngestor(), URLIngestor()]


def pick_ingestor(source: Source) -> Optional[Ingestor]:
    for ing in get_ingestors():
        if ing.can_handle(source):
            return ing
    return None


def get_retriever() -> Retriever:
    return GrepRetriever()


def get_browser(*, trace_dir: Optional[Path] = None) -> BrowserAdapter:
    """Default browser adapter: Playwright (Python sync API)."""
    return PlaywrightAdapter(trace_dir=trace_dir)


def get_runner(language: str = "python") -> TestRunner:
    if language in ("python", "auto"):
        return PytestRunner()
    raise NotImplementedError(f"Runner for language={language} not yet implemented (v0.2)")


def get_reporter(format: str = "markdown") -> Reporter:
    if format in ("markdown", "md"):
        return MarkdownReporter()
    raise NotImplementedError(f"Reporter for format={format} not yet implemented (v0.2)")


def get_reviewer(timing: str = "post_turn") -> Reviewer:
    if timing == "post_turn":
        return PostTurnReviewer()
    raise NotImplementedError(f"Reviewer for timing={timing} not yet implemented (v0.3)")


__all__ = [
    "get_ingestors", "pick_ingestor",
    "get_retriever",
    "get_browser",
    "get_runner",
    "get_reporter",
    "get_reviewer",
]
