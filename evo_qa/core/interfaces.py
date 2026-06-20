"""
L4 Interfaces — abstract protocols.

All adapters must implement these Protocols. The Orchestrator talks only to
Protocols; it does not know the concrete implementations.

Adding a new adapter = implement the Protocol + register it in `registry.py`.
No other code needs to change.

See references/VISION.md for the layering rationale.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from .schemas import Change, Finding, Knowledge, Run, Spec


# =====================
# Source — input material reference
# =====================

class Source:
    """Unified abstraction for an input material."""

    def __init__(
        self,
        kind: Literal["file", "directory", "url", "text", "git"],
        location: str,
        meta: dict[str, Any] | None = None,
    ):
        self.kind = kind
        self.location = location
        self.meta = meta or {}

    def __repr__(self) -> str:
        return f"Source(kind={self.kind}, location={self.location[:60]}...)"


# =====================
# Snapshot — browser snapshot
# =====================

class Snapshot:
    """Unified snapshot representation of a browser page."""

    def __init__(
        self,
        url: str,
        title: str,
        accessibility_tree: str = "",   # accessibility tree text (similar to Playwright's snapshot)
        elements: list[dict] | None = None,  # [{ref, role, name, ...}, ...]
        screenshot_path: str = "",
        console_logs: list[str] | None = None,
    ):
        self.url = url
        self.title = title
        self.accessibility_tree = accessibility_tree
        self.elements = elements or []
        self.screenshot_path = screenshot_path
        self.console_logs = console_logs or []


# =====================
# Ingestor — material digestion
# =====================

@runtime_checkable
class Ingestor(Protocol):
    """Turn a Source into a list of Knowledge entries."""

    name: str  # adapter identifier

    def can_handle(self, source: Source) -> bool:
        """Can this ingestor handle this source?"""
        ...

    def ingest(self, source: Source) -> list[Knowledge]:
        """Digest → produce Knowledge entries."""
        ...


# =====================
# Retriever — knowledge retrieval
# =====================

@runtime_checkable
class Retriever(Protocol):
    """Retrieve relevant Knowledge from the knowledge base."""

    name: str

    def index(self, knowledge_dirs: list[Path]) -> None:
        """Build an index, if the implementation needs one."""
        ...

    def search(
        self,
        query: str,
        scope: list[str] | None = None,    # ["industry", "project"]
        tags: list[str] | None = None,
        top_k: int = 5,
    ) -> list[Knowledge]:
        ...


# =====================
# BrowserAdapter — browser execution
# =====================

@runtime_checkable
class BrowserAdapter(Protocol):
    """Unified browser interface. Playwright / browser_use / playwright-cli are all valid implementations."""

    name: str

    def start(self, *, headed: bool = False) -> None: ...
    def stop(self) -> None: ...

    def open(self, url: str) -> None: ...
    def goto(self, url: str) -> None: ...
    def snapshot(self) -> Snapshot: ...

    # interactions
    def click(self, ref: str) -> None: ...
    def type(self, ref: str, text: str, *, submit: bool = False) -> None: ...
    def fill(self, ref: str, text: str) -> None: ...
    def press(self, key: str) -> None: ...

    # observations
    def screenshot(self, path: str) -> None: ...
    def get_url(self) -> str: ...
    def get_title(self) -> str: ...
    def evaluate(self, expr: str) -> Any: ...

    # state
    def wait_for_load(self) -> None: ...


# =====================
# TestRunner — test generation + execution
# =====================

ProjectType = Literal["python-pytest", "typescript-playwright", "unknown"]
Language = Literal["python", "typescript"]


@runtime_checkable
class TestRunner(Protocol):
    """Generate standalone test scripts from a Change and execute them."""

    name: str
    language: Language

    def detect_project(self, root: Path) -> ProjectType:
        """Detect the project kind (e.g. package.json + @playwright/test → ts; pyproject.toml + pytest → python)."""
        ...

    def render(self, change: Change, output_dir: Path) -> Path:
        """Render to a test script and return the path."""
        ...

    def execute(self, test_path: Path, *, headed: bool = False) -> Run:
        """Execute the tests and return a Run result."""
        ...


# =====================
# Reporter — report rendering
# =====================

ReportFormat = Literal["markdown", "html", "json"]


@runtime_checkable
class Reporter(Protocol):
    """Turn a Run into a report."""

    name: str
    formats: list[ReportFormat]

    def render(self, run: Run, change: Change, format: ReportFormat, output_dir: Path) -> Path:
        ...


# =====================
# Reviewer — self-reflection (inspired by Hermes)
# =====================

@runtime_checkable
class Reviewer(Protocol):
    """Periodic retrospective that distills knowledge."""

    name: str
    timing: Literal["post_turn", "post_change", "periodic"]

    def review(self, context: dict[str, Any]) -> list[Knowledge]:
        """
        Review a slice of work and produce new Knowledge entries
        (which are inserted into the project brain).

        The context dict carries at least:
          - workspace_path: Path
          - recent_runs: list[Run] (optional)
          - recent_changes: list[Change] (optional)
        """
        ...


__all__ = [
    "Source", "Snapshot",
    "Ingestor", "Retriever",
    "BrowserAdapter", "ProjectType", "Language",
    "TestRunner", "Reporter", "ReportFormat",
    "Reviewer",
]
