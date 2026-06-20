"""
Playwright BrowserAdapter — implements BrowserAdapter via Playwright's sync API.

The default browser executor.

Design notes:
- Uses `sync_playwright` (the orchestrator is synchronous).
- Provides a `ref` abstraction (internally mapped to a selector) so the
  agent can act on semantic references rather than raw CSS.
- snapshot returns the accessibility tree + a list of interactive elements
- every action is traced and replayable on failure
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Optional

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)

from ...core.interfaces import BrowserAdapter, Snapshot


class PlaywrightAdapter:
    """BrowserAdapter implementation backed by Playwright (Python sync API)."""

    name = "playwright"

    def __init__(self, *, browser: str = "chromium", trace_dir: Optional[Path] = None):
        self._browser_kind = browser
        self._trace_dir = trace_dir
        self._pw: Optional[Playwright] = None
        self._b: Optional[Browser] = None
        self._ctx: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._console_logs: list[str] = []
        # ref -> selector mapping
        self._ref_map: dict[str, str] = {}
        self._ref_counter = 0

    # ---- lifecycle ----

    def start(self, *, headed: bool = False) -> None:
        if self._pw is not None:
            return
        self._pw = sync_playwright().start()
        launcher = getattr(self._pw, self._browser_kind)
        self._b = launcher.launch(headless=not headed)
        # ignore_https_errors: critical for enterprise/sandbox environments
        # behind internal CAs (e.g., internal corporate sites). Safe for QA contexts.
        self._ctx = self._b.new_context(ignore_https_errors=True)
        if self._trace_dir is not None:
            self._trace_dir.mkdir(parents=True, exist_ok=True)
            self._ctx.tracing.start(screenshots=True, snapshots=True, sources=True)
        self._page = self._ctx.new_page()
        self._page.on("console", lambda msg: self._console_logs.append(f"[{msg.type}] {msg.text}"))

    def stop(self) -> None:
        if self._ctx and self._trace_dir:
            try:
                self._ctx.tracing.stop(path=str(self._trace_dir / "trace.zip"))
            except Exception:
                pass
        for closer in (self._ctx, self._b, self._pw):
            if closer is None:
                continue
            try:
                closer.close() if hasattr(closer, "close") else closer.stop()
            except Exception:
                pass
        self._pw = self._b = self._ctx = self._page = None

    # ---- navigation ----

    def open(self, url: str) -> None:
        self.goto(url)

    def goto(self, url: str) -> None:
        assert self._page is not None, "Call start() first"
        self._page.goto(url, wait_until="domcontentloaded")

    def wait_for_load(self) -> None:
        assert self._page is not None
        self._page.wait_for_load_state("networkidle", timeout=10000)

    # ---- snapshot ----

    def snapshot(self) -> Snapshot:
        """
        Return a page snapshot, including:
        - page metadata
        - the list of interactive elements (each tagged with a ref, recorded in _ref_map)
        - a simplified, human-readable accessibility tree
        """
        assert self._page is not None
        page = self._page

        # Reset the ref map
        self._ref_map = {}
        self._ref_counter = 0

        # Collect all interactive elements + their labels
        elements_data = page.evaluate(
            r"""
            () => {
                const results = [];
                const selectors = [
                    'a[href]', 'button', 'input', 'select', 'textarea',
                    '[role="button"]', '[role="link"]', '[role="textbox"]',
                    '[role="checkbox"]', '[role="radio"]', '[onclick]',
                ];
                const seen = new Set();
                for (const sel of selectors) {
                    document.querySelectorAll(sel).forEach((el) => {
                        if (seen.has(el)) return;
                        seen.add(el);
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) return;
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') return;

                        const text = (el.innerText || el.value || el.placeholder || '').trim().slice(0, 80);
                        const role = el.getAttribute('role') || el.tagName.toLowerCase();
                        const id = el.id || '';
                        const dataTest = el.getAttribute('data-test') || el.getAttribute('data-testid') || '';
                        const name = el.getAttribute('name') || '';
                        const type = el.getAttribute('type') || '';
                        const cls = el.className && typeof el.className === 'string' ? el.className.slice(0, 60) : '';

                        results.push({ role, text, id, dataTest, name, type, cls });
                    });
                }
                return results;
            }
            """
        )

        elements = []
        for d in elements_data:
            self._ref_counter += 1
            ref = f"e{self._ref_counter}"

            # Pick the most stable selector (priority: data-test > id > role+text)
            sel = self._build_selector(d)
            if not sel:
                continue
            self._ref_map[ref] = sel

            elements.append({
                "ref": ref,
                "role": d.get("role", ""),
                "name": d.get("text", "") or d.get("name", "") or d.get("dataTest", ""),
                "selector": sel,
                "type": d.get("type", ""),
            })

        # Build a readable (simplified) accessibility tree
        lines = []
        for e in elements:
            lines.append(f"- [{e['ref']}] {e['role']} \"{e['name']}\"  → {e['selector']}")
        tree = "\n".join(lines)

        # screenshot
        ss_path = ""
        if self._trace_dir:
            ss_path = str(self._trace_dir / f"snapshot-{len(list(self._trace_dir.glob('snapshot-*.png')))}.png")
            page.screenshot(path=ss_path)

        return Snapshot(
            url=page.url,
            title=page.title(),
            accessibility_tree=tree,
            elements=elements,
            screenshot_path=ss_path,
            console_logs=list(self._console_logs),
        )

    def _build_selector(self, d: dict) -> str:
        """Build the most stable selector from element attributes."""
        if d.get("dataTest"):
            return f'[data-test="{d["dataTest"]}"]'
        if d.get("id"):
            return f'#{d["id"]}'
        if d.get("name"):
            return f'[name="{d["name"]}"]'
        if d.get("role") in ("button", "a", "link"):
            t = d.get("text", "").strip()
            if t:
                return f'role={d["role"]}[name="{t}"]'
        return ""

    # ---- interactions ----

    def _resolve(self, ref: str) -> str:
        if ref in self._ref_map:
            return self._ref_map[ref]
        # Allow passing a raw selector directly
        return ref

    def click(self, ref: str) -> None:
        assert self._page is not None
        sel = self._resolve(ref)
        self._page.click(sel, timeout=10000)

    def type(self, ref: str, text: str, *, submit: bool = False) -> None:
        self.fill(ref, text)
        if submit:
            self._page.keyboard.press("Enter")

    def fill(self, ref: str, text: str) -> None:
        assert self._page is not None
        sel = self._resolve(ref)
        self._page.fill(sel, text, timeout=10000)

    def press(self, key: str) -> None:
        assert self._page is not None
        self._page.keyboard.press(key)

    # ---- observations ----

    def screenshot(self, path: str) -> None:
        assert self._page is not None
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._page.screenshot(path=path)

    def get_url(self) -> str:
        assert self._page is not None
        return self._page.url

    def get_title(self) -> str:
        assert self._page is not None
        return self._page.title()

    def evaluate(self, expr: str) -> Any:
        assert self._page is not None
        return self._page.evaluate(expr)


__all__ = ["PlaywrightAdapter"]
