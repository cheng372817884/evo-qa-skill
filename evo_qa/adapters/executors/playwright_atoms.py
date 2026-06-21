"""
Playwright Atom Executor — implementation of every atom for real browsers.

Loads Playwright lazily so importing this module doesn't require it.
Each atom is a small method; the dispatcher in `run()` picks the right one.

The executor also exposes:
  - emergency_screenshot(ctx, path)   — used by the watchdog on timeout
  - propose_alternates(atom, ctx)     — heuristic healer hook
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional

from ...core.atoms import Atom, AtomResult, ExecutionContext


class PlaywrightAtomExecutor:
    name = "playwright"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    # -- lifecycle --------------------------------------------------------

    def setup(self, ctx: ExecutionContext) -> None:
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=not ctx.headed and self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = self._browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1440, "height": 900},
        )
        self._context.set_default_timeout(ctx.timeout_ms)
        self._page = self._context.new_page()
        Path(ctx.evidence_dir).mkdir(parents=True, exist_ok=True)

    def teardown(self, ctx: ExecutionContext) -> None:
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._pw = None

    # -- helpers ----------------------------------------------------------

    @property
    def page(self):
        if self._page is None:
            raise RuntimeError("Executor not set up — call setup() first")
        return self._page

    def emergency_screenshot(self, ctx: ExecutionContext, path: str) -> None:
        """Best-effort screenshot from another thread (watchdog timeout)."""
        if self._page is None:
            return
        try:
            self._page.screenshot(path=path, full_page=False, timeout=2000)
        except Exception:
            pass

    def _shot(self, ctx: ExecutionContext, label: str) -> str:
        out = Path(ctx.evidence_dir) / f"{label}.png"
        try:
            self.page.screenshot(path=str(out), full_page=False)
            return str(out)
        except Exception:
            return ""

    def _classify(self, exc: BaseException) -> str:
        msg = str(exc).lower()
        cls = type(exc).__name__.lower()
        if "timeout" in cls or "timeout" in msg:
            return "timeout"
        if "no node" in msg or "selector" in msg or "not found" in msg or "did not find" in msg:
            return "selector_not_found"
        if "not visible" in msg or "hidden" in msg:
            return "element_not_visible"
        if "stale" in msg:
            return "stale_element"
        if "navigation" in msg or "navigate" in msg or "net::" in msg:
            return "navigation"
        if "closed" in msg:
            return "page_closed"
        if "disconnect" in msg:
            return "disconnected"
        return "unknown"

    # -- atom dispatcher --------------------------------------------------

    def run(self, atom: Atom, ctx: ExecutionContext) -> AtomResult:
        start = time.monotonic()
        method = getattr(self, f"_atom_{atom.name}", None)
        if method is None:
            return AtomResult(ok=False, error_kind="unknown",
                              error_msg=f"No impl for atom {atom.name!r}")
        try:
            extra = method(atom, ctx) or {}
            wall = int((time.monotonic() - start) * 1000)
            return AtomResult(ok=True, wall_ms=wall, extra=extra)
        except Exception as e:
            wall = int((time.monotonic() - start) * 1000)
            kind = self._classify(e)
            shot = self._shot(ctx, f"fail-{atom.step_id or atom.name}")
            return AtomResult(
                ok=False, error_kind=kind,
                error_msg=f"{type(e).__name__}: {e}"[:500],
                wall_ms=wall, screenshot_path=shot,
            )

    # -- atom impls -------------------------------------------------------

    def _atom_goto(self, atom: Atom, ctx: ExecutionContext) -> dict:
        url = atom.target or ""
        wait = atom.options.get("wait_until", "domcontentloaded")
        self.page.goto(url, wait_until=wait,
                       timeout=atom.options.get("timeout_ms",
                                                ctx.timeout_ms))
        return {"final_url": self.page.url}

    def _atom_click(self, atom: Atom, ctx: ExecutionContext) -> dict:
        sel = atom.target or ""
        self.page.locator(sel).first.click(
            timeout=atom.options.get("timeout_ms", ctx.timeout_ms),
            force=atom.options.get("force", False),
        )
        return {}

    def _atom_fill(self, atom: Atom, ctx: ExecutionContext) -> dict:
        sel = atom.target or ""
        self.page.locator(sel).first.fill(
            atom.value or "",
            timeout=atom.options.get("timeout_ms", ctx.timeout_ms),
        )
        return {}

    def _atom_press(self, atom: Atom, ctx: ExecutionContext) -> dict:
        key = atom.value or ""
        if atom.target:
            self.page.locator(atom.target).first.press(
                key, timeout=atom.options.get("timeout_ms", ctx.timeout_ms))
        else:
            self.page.keyboard.press(key)
        return {}

    def _atom_expect_visible(self, atom: Atom, ctx: ExecutionContext) -> dict:
        from playwright.sync_api import expect
        sel = atom.target or ""
        expect(self.page.locator(sel).first).to_be_visible(
            timeout=atom.options.get("timeout_ms", ctx.timeout_ms))
        return {}

    def _atom_expect_text(self, atom: Atom, ctx: ExecutionContext) -> dict:
        from playwright.sync_api import expect
        sel = atom.target or ""
        text = atom.value or ""
        # use to_contain_text — most useful in practice
        expect(self.page.locator(sel).first).to_contain_text(
            text, timeout=atom.options.get("timeout_ms", ctx.timeout_ms))
        return {}

    def _atom_expect_url(self, atom: Atom, ctx: ExecutionContext) -> dict:
        pattern = atom.value or ""
        # Tolerate substring or regex
        if atom.options.get("regex"):
            from playwright.sync_api import expect
            expect(self.page).to_have_url(
                re.compile(pattern),
                timeout=atom.options.get("timeout_ms", ctx.timeout_ms))
        else:
            current = self.page.url
            if pattern not in current:
                # raise an assertion-style error so classifier marks it functional
                raise AssertionError(
                    f"URL {current!r} does not contain {pattern!r}")
        return {"final_url": self.page.url}

    def _atom_wait_for(self, atom: Atom, ctx: ExecutionContext) -> dict:
        sel = atom.target or ""
        state = atom.options.get("state", "visible")
        self.page.locator(sel).first.wait_for(
            state=state,
            timeout=atom.options.get("timeout_ms", ctx.timeout_ms))
        return {}

    def _atom_select(self, atom: Atom, ctx: ExecutionContext) -> dict:
        sel = atom.target or ""
        self.page.locator(sel).first.select_option(
            value=atom.value,
            timeout=atom.options.get("timeout_ms", ctx.timeout_ms))
        return {}

    def _atom_select_option_smart(self, atom: Atom,
                                  ctx: ExecutionContext) -> dict:
        """Universal dropdown picker — 5-tier fallback.

        Order (most reliable → most defensive):
          1. Native <select>          → selectOption()
          2. type-to-filter           → fill + click result    (combobox/searchbox/input)
          3. already-rendered option  → scrollIntoView + click
          4. virtualized scroll-loop  → scroll container, re-check, terminate on no-progress
          5. keyboard navigation      → ArrowDown × N + Enter

        See knowledge/_imported/pitfall-virtualized-dropdown.md for
        background and references.
        """
        from playwright.sync_api import TimeoutError as PWTimeout

        trigger = atom.target or ""
        value = atom.value or ""
        opts = atom.options or {}
        timeout = opts.get("timeout_ms", ctx.timeout_ms)
        short = min(3000, timeout)
        page = self.page

        container_sel = opts.get("dropdown_container") or "[role=listbox]"
        opt_tpl = (opts.get("option_selector")
                   or '[role=option]:has-text("{value}")')
        opt_sel = opt_tpl.replace("{value}", value)
        max_scrolls = int(opts.get("max_scrolls", 40))
        prefer_keyboard = bool(opts.get("prefer_keyboard", False))

        trail = []   # for evidence

        def log(tier, note):
            trail.append({"tier": tier, "note": note})

        # -- Tier 1: native <select> ----------------------------------------
        try:
            tag = page.locator(trigger).first.evaluate(
                "el => el.tagName", timeout=short)
            if tag == "SELECT":
                page.locator(trigger).first.select_option(
                    label=value, timeout=timeout)
                log(1, "native <select>")
                return {"tier": 1, "trail": trail}
        except Exception:
            pass

        # Open the dropdown
        page.locator(trigger).first.click(timeout=timeout)
        try:
            page.wait_for_selector(container_sel, state="attached",
                                   timeout=short)
        except PWTimeout:
            # Some libraries don't expose role=listbox immediately;
            # we'll let later tiers try anyway.
            log(0, f"container {container_sel} not attached, continuing")

        # -- Tier 2: type-to-filter -----------------------------------------
        if not prefer_keyboard:
            try:
                role = (page.locator(trigger).first.get_attribute(
                    "role", timeout=short) or "")
                tag = page.locator(trigger).first.evaluate(
                    "el => el.tagName", timeout=short)
                if role in ("combobox", "searchbox") or tag == "INPUT":
                    page.locator(trigger).first.fill(value, timeout=short)
                    page.wait_for_selector(opt_sel, timeout=short)
                    page.locator(opt_sel).first.click(timeout=short)
                    log(2, "type-to-filter")
                    return {"tier": 2, "trail": trail}
            except Exception as e:
                log(2, f"miss: {type(e).__name__}")

        # -- Tier 3: already-rendered option --------------------------------
        try:
            if page.locator(opt_sel).count() > 0:
                page.locator(opt_sel).first.scroll_into_view_if_needed(
                    timeout=short)
                page.locator(opt_sel).first.click(timeout=short)
                log(3, "rendered + scrollIntoView")
                return {"tier": 3, "trail": trail}
        except Exception as e:
            log(3, f"miss: {type(e).__name__}")

        # -- Tier 4: virtualized scroll-loop --------------------------------
        # Scroll only the dropdown container — never the page/modal.
        log(4, f"start: scrolling {container_sel} up to {max_scrolls}x")
        last_first_text = None
        scroll_err = None
        scrolls_done = 0
        for i in range(max_scrolls):
            scrolls_done = i
            try:
                if page.locator(opt_sel).count() > 0:
                    page.locator(opt_sel).first.scroll_into_view_if_needed(
                        timeout=short)
                    page.locator(opt_sel).first.click(timeout=short)
                    log(4, f"hit @ scroll {i}")
                    return {"tier": 4, "trail": trail, "scrolls": i}
            except Exception as e:
                scroll_err = f"click: {type(e).__name__}"
            try:
                page.locator(container_sel).first.evaluate(
                    "el => { el.scrollTop = el.scrollTop + el.clientHeight * 0.8; }",
                    timeout=short,
                )
            except Exception as e:
                scroll_err = f"scroll: {type(e).__name__}: {e}"
                break
            page.wait_for_timeout(120)
            try:
                first_text = page.locator(
                    f"{container_sel} >> [role=option]"
                ).first.text_content(timeout=short)
            except Exception:
                first_text = None
            if first_text == last_first_text and i > 0:
                log(4, f"no-progress @ scroll {i} (first={first_text!r})")
                break
            last_first_text = first_text
        log(4, f"exhausted after {scrolls_done+1} scrolls; "
               f"last_first={last_first_text!r}; err={scroll_err}")

        # -- Tier 5: keyboard navigation ------------------------------------
        try:
            # Re-open to reset highlight
            page.locator(trigger).first.click(timeout=short)
        except Exception:
            pass
        for _ in range(max_scrolls * 3):
            page.keyboard.press("ArrowDown")
            try:
                active = page.evaluate(
                    "() => document.activeElement && "
                    "(document.activeElement.textContent || '').trim()"
                )
            except Exception:
                active = None
            if active and value in active:
                page.keyboard.press("Enter")
                log(5, f"keyboard hit '{active}'")
                return {"tier": 5, "trail": trail}

        # All tiers exhausted
        raise Exception(
            f"select_option_smart: '{value}' not found via "
            f"any tier (trail={trail})"
        )

    def _atom_screenshot(self, atom: Atom, ctx: ExecutionContext) -> dict:
        label = atom.value or atom.step_id or "snap"
        out = Path(ctx.evidence_dir) / f"{label}.png"
        self.page.screenshot(path=str(out),
                             full_page=atom.options.get("full_page", False))
        return {"screenshot_path": str(out)}

    def _atom_evaluate(self, atom: Atom, ctx: ExecutionContext) -> dict:
        script = atom.value or "() => null"
        result = self.page.evaluate(script)
        return {"result": result}

    def _atom_noop(self, atom: Atom, ctx: ExecutionContext) -> dict:
        # Test-only: options.fail_with -> raise that error class
        if "fail_with" in atom.options:
            raise RuntimeError(atom.options["fail_with"])
        return {"label": atom.value or ""}

    # -- healer hook ------------------------------------------------------

    def propose_alternates(self, atom: Atom,
                           ctx: ExecutionContext) -> list[Atom]:
        """Heuristic healer — propose alternate selectors for click/fill/expect_visible.

        Strategies (best to worst):
          1. drop ':nth-child(...)' positional segments
          2. if selector starts with '#' or '[id=', try '[name=...]' / '[aria-label=...]' from DOM hint
          3. if selector is text-based, try getByRole equivalents (role hint required from atom.options)
        """
        if atom.name not in ("click", "fill", "expect_visible",
                             "expect_text", "wait_for"):
            return []
        sel = atom.target or ""
        if not sel:
            return []
        proposals: list[Atom] = []

        # Strategy 1 — strip nth-child
        loosened = re.sub(r":nth-(?:child|of-type)\([^)]*\)", "", sel).strip()
        if loosened and loosened != sel:
            proposals.append(self._with_target(atom, loosened))

        # Strategy 2 — id → fallback to provided role/name/text in options
        role = atom.options.get("_role")
        name = atom.options.get("_name")
        if role and name:
            # Playwright's role selector
            new_sel = f"role={role}[name=\"{name}\"]"
            proposals.append(self._with_target(atom, new_sel))

        # Strategy 3 — text-based fallback
        text_hint = atom.options.get("_text")
        if text_hint:
            proposals.append(self._with_target(atom, f"text={text_hint}"))

        return proposals

    @staticmethod
    def _with_target(atom: Atom, new_target: str) -> Atom:
        return Atom(
            name=atom.name, target=new_target, value=atom.value,
            options=dict(atom.options), description=f"[healed] {atom.description}",
            step_id=atom.step_id + ".heal",
        )


__all__ = ["PlaywrightAtomExecutor"]
