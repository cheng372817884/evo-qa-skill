"""
Atoms — standardised, stateless execution units.

A test plan is a list of Atoms. An Executor adapter (Playwright today,
maybe Selenium tomorrow) knows how to run each atom against a real browser.
The orchestrator only ever speaks Atoms — it never touches the browser API.

This is the contract that makes everything else swappable.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Callable, Protocol


# Canonical atom names. Add new ones here; adapters MUST implement all.
ATOM_NAMES = (
    "goto",            # navigate to URL
    "click",           # click an element
    "fill",            # type into an input
    "press",           # press a key (Enter, Tab, Escape, …)
    "expect_visible",  # assert element is visible
    "expect_text",     # assert element contains text
    "expect_url",      # assert URL matches (substring or regex)
    "wait_for",        # wait until selector appears or timeout
    "select",          # <select> option pick
    "select_option_smart",  # universal dropdown (5-tier fallback for virtualized/custom)
    "screenshot",      # take a screenshot to evidence dir
    "evaluate",        # run JS in page (advanced)
    "noop",            # no-op marker (used in tests)
)


@dataclass
class Atom:
    """A single declarative test step."""

    name: str
    target: Optional[str] = None      # CSS / URL / key / etc.
    value: Optional[str] = None       # text-to-type, expected text, etc.
    options: dict = field(default_factory=dict)
    description: str = ""             # human-readable for reports
    step_id: str = ""                 # populated by orchestrator (e.g. "step-3")

    def __post_init__(self):
        if self.name not in ATOM_NAMES:
            raise ValueError(
                f"Unknown atom name: {self.name!r}. "
                f"Allowed: {ATOM_NAMES}"
            )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Atom":
        return cls(**d)


@dataclass
class AtomResult:
    """The outcome of executing one Atom."""

    ok: bool
    error_kind: str = ""              # 'timeout' | 'selector_not_found' | 'assertion' | 'navigation' | 'unknown'
    error_msg: str = ""
    wall_ms: int = 0
    screenshot_path: str = ""
    extra: dict = field(default_factory=dict)   # adapter-specific (e.g. last-seen-role)


@dataclass
class ExecutionContext:
    """Shared state passed to every atom call.

    The adapter decides what to put in here (page, browser, evidence_dir).
    Orchestrator only reads top-level attributes.
    """

    run_id: str
    project: str
    evidence_dir: str
    timeout_ms: int = 30000
    headed: bool = False
    state: dict = field(default_factory=dict)   # adapter scratch-pad


class AtomExecutor(Protocol):
    """An adapter that knows how to run atoms.

    Adapters need not handle retry/watchdog — RetryDriver wraps the call.
    """

    name: str

    def setup(self, ctx: ExecutionContext) -> None: ...

    def run(self, atom: Atom, ctx: ExecutionContext) -> AtomResult: ...

    def teardown(self, ctx: ExecutionContext) -> None: ...

    # Optional — if implemented, healer can use it.
    # def propose_alternates(self, atom: Atom, ctx: ExecutionContext) -> list[Atom]: ...


# Convenience constructors so plans read like English -----------------------

def goto(url: str, *, description: str = "", **opts) -> Atom:
    return Atom(name="goto", target=url, options=opts,
                description=description or f"Navigate to {url}")


def click(selector: str, *, description: str = "", **opts) -> Atom:
    return Atom(name="click", target=selector, options=opts,
                description=description or f"Click {selector}")


def fill(selector: str, value: str, *, description: str = "", **opts) -> Atom:
    return Atom(name="fill", target=selector, value=value, options=opts,
                description=description or f"Type into {selector}")


def press(key: str, *, target: str = "", description: str = "", **opts) -> Atom:
    return Atom(name="press", target=target, value=key, options=opts,
                description=description or f"Press {key}")


def expect_visible(selector: str, *, description: str = "", **opts) -> Atom:
    return Atom(name="expect_visible", target=selector, options=opts,
                description=description or f"Expect visible: {selector}")


def expect_text(selector: str, text: str, *, description: str = "", **opts) -> Atom:
    return Atom(name="expect_text", target=selector, value=text, options=opts,
                description=description or f"Expect '{text}' in {selector}")


def expect_url(pattern: str, *, description: str = "", **opts) -> Atom:
    return Atom(name="expect_url", value=pattern, options=opts,
                description=description or f"Expect URL ~ {pattern}")


def wait_for(selector: str, *, description: str = "", **opts) -> Atom:
    return Atom(name="wait_for", target=selector, options=opts,
                description=description or f"Wait for {selector}")


def screenshot(name: str = "step", **opts) -> Atom:
    return Atom(name="screenshot", value=name, options=opts,
                description=f"Screenshot: {name}")


def select_option_smart(trigger: str, value: str, *,
                        dropdown_container: str = "",
                        option_selector: str = "",
                        max_scrolls: int = 40,
                        prefer_keyboard: bool = False,
                        description: str = "",
                        **opts) -> Atom:
    """Universal dropdown picker — handles native, combobox, virtualized.

    `trigger` is the element you click to open the dropdown.
    `value` is the option's visible text.
    `dropdown_container` (optional) — listbox container CSS; default [role=listbox].
    `option_selector` (optional) — option template with {value} placeholder;
        default [role=option]:has-text("{value}")
    `max_scrolls` — virtualization scroll cap (default 20)
    `prefer_keyboard` — skip type-to-filter, go straight to ArrowDown nav
    """
    options = {
        "dropdown_container": dropdown_container,
        "option_selector": option_selector,
        "max_scrolls": max_scrolls,
        "prefer_keyboard": prefer_keyboard,
        **opts,
    }
    return Atom(name="select_option_smart", target=trigger, value=value,
                options=options,
                description=description or f"Pick '{value}' from dropdown {trigger}")


def noop(label: str = "noop", **opts) -> Atom:
    """Test-only atom that succeeds or fails based on options."""
    return Atom(name="noop", value=label, options=opts, description=label)


__all__ = [
    "Atom", "AtomResult", "AtomExecutor", "ExecutionContext", "ATOM_NAMES",
    "goto", "click", "fill", "press", "expect_visible", "expect_text",
    "expect_url", "wait_for", "screenshot", "select_option_smart", "noop",
]
