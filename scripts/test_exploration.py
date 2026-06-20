"""
test_exploration.py — locks down ExplorerLoop + MemoryGate + Strategies
+ Guards behavior end-to-end, without a real browser.

We use a MockDriver that maintains a fake browser state machine
matching saucedemo's login flow:

  Initial            → /login page with username/password/button
  fill+wrong+click   → /login page WITH error text "Epic sadface..."
  fill+right+click   → /inventory page (different elements + URL)

Invariants locked down (DO NOT REGRESS):

  E1  MemoryGate empty store → full exploration
  E2  MemoryGate rich brain  → skip=True, proceed_to=plan
  E3  MemoryGate medium      → partial (gaps reported)
  E4  Login strategy state machine: 7 phases
  E5  ExplorerLoop happy path on saucedemo mock: status=completed,
      LOGIN_SUCCESS note recorded, /inventory in pages_discovered
  E6  Wrong-creds path captures LOGIN_ERROR_VISIBLE signal
  E7  BlacklistGuard silently skips a "Delete" button
  E8  AlreadyDoneGuard prevents infinite loops
  E9  OriginGuard blocks navigation to evil.com
  E10 read_only=True → no fill/click executes (driver method count==1
      for the initial navigate only)
  E11 Strategy returning stop on no-form: status=completed, 1 step
  E12 ExplorationReport renders to readable Markdown with steps section
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from evo_qa.core.exploration import (
    Charter, MemoryGate, ExplorerLoop, render_report,
    list_strategies, get_strategy,
)
from evo_qa.core.exploration.schemas import (
    Snapshot, ElementRef, Action, ExplorationStep,
)
from evo_qa.core.exploration.guards import (
    BlacklistGuard, OriginGuard, AlreadyDoneGuard, evaluate_all,
)


# ---------------------------------------------------------------------------
# Mock driver — simulates a 2-page saucedemo
# ---------------------------------------------------------------------------

class _SnapAdapter:
    def __init__(self, url: str, title: str, elements: list) -> None:
        self.url = url
        self.title = title
        self.elements = elements


class MockDriver:
    """A minimal Playwright-shaped fake."""

    LOGIN_ELEMENTS = [
        {"role": "textbox", "name": "Username",
         "selector": "#user-name", "text": "",
         "attrs": {"id": "user-name", "type": "text"}},
        {"role": "textbox", "name": "Password",
         "selector": "#password", "text": "",
         "attrs": {"id": "password", "type": "password"}},
        {"role": "button", "name": "Login",
         "selector": "#login-button", "text": "LOGIN",
         "attrs": {"id": "login-button", "type": "submit"}},
    ]

    INVENTORY_ELEMENTS = [
        {"role": "link", "name": "Sauce Labs Backpack",
         "selector": "a.inventory_item_name", "text": "Sauce Labs Backpack",
         "attrs": {}},
        {"role": "button", "name": "Add to cart",
         "selector": ".btn_inventory", "text": "ADD TO CART",
         "attrs": {}},
        {"role": "link", "name": "Cart", "selector": ".shopping_cart_link",
         "text": "", "attrs": {}},
    ]

    def __init__(self) -> None:
        self.url = ""
        self.method_calls: list[str] = []
        self._username = ""
        self._password = ""
        self._submitted = False
        self._wrong_submitted = False

    # ---- public methods ExplorerLoop calls ----
    def goto(self, url: str) -> None:
        self.method_calls.append(f"goto:{url}")
        self.url = url
        self._username = ""
        self._password = ""
        self._submitted = False

    def wait_for_load(self) -> None:
        self.method_calls.append("wait_for_load")

    def fill(self, sel: str, value: str) -> None:
        self.method_calls.append(f"fill:{sel}:{value}")
        if sel == "#user-name":
            self._username = value
        elif sel == "#password":
            self._password = value

    def click(self, sel: str) -> None:
        self.method_calls.append(f"click:{sel}")
        if sel == "#login-button":
            if (self._username == "standard_user"
                    and self._password == "secret_sauce"):
                self.url = "https://www.saucedemo.com/inventory.html"
                self._submitted = True
            else:
                self._wrong_submitted = True

    def press(self, sel: str, key: str) -> None:
        self.method_calls.append(f"press:{sel}:{key}")

    def stop(self) -> None:
        self.method_calls.append("stop")

    def snapshot(self) -> _SnapAdapter:
        if "inventory" in self.url:
            return _SnapAdapter(
                url=self.url, title="Products",
                elements=list(self.INVENTORY_ELEMENTS),
            )
        # Login page
        elements = list(self.LOGIN_ELEMENTS)
        if self._wrong_submitted:
            elements = elements + [{
                # B6 (v1.1.1): post-fix, error detection requires
                # role=alert/status — this matches real-world
                # ARIA-correct error UIs and avoids false positives
                # from element names. saucedemo's actual DOM uses
                # h3[data-test=error] with role="alert" since v2.
                "role": "alert", "name": "",
                "selector": "[data-test=error]",
                "text": "Epic sadface: Username and password do not match",
                "attrs": {},
            }]
        return _SnapAdapter(
            url=self.url or "https://www.saucedemo.com",
            title="Swag Labs Login",
            elements=elements,
        )


def make_factory(driver):
    def factory(headed: bool):
        return driver
    return factory


def make_cred_resolver(username: str, password: str):
    def resolve(entry_id: str):
        return {"username": username, "password": password}
    return resolve


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _mock_ws(root):
    class Ws:
        pass
    ws = Ws()
    p = Path(root)
    ws.selectors_path = p / "selectors.json"
    ws.pages_path = p / "pages.md"
    ws.brain_dir = p / "brain"
    ws.brain_dir.mkdir(parents=True, exist_ok=True)
    return ws


def test_e1_memory_gate_empty():
    ws = _mock_ws(tempfile.mkdtemp())
    gate = MemoryGate(ws)
    need = gate.assess(Charter(raw="login", kind="login",
                               target_url="https://x"))
    assert need.skip is False
    assert need.scope == "full"
    assert need.coverage.score == 0.0
    print("✓ E1 empty memory → full exploration")


def test_e2_memory_gate_rich():
    ws = _mock_ws(tempfile.mkdtemp())
    ws.selectors_path.write_text(json.dumps({"selectors": {
        "textbox:Username": {"selector": "#u", "score": 1.0,
                             "first_seen": "2026-06-15T00:00:00Z"},
        "textbox:Password": {"selector": "#p", "score": 1.0,
                             "first_seen": "2026-06-15T00:00:00Z"},
        "button:Login":     {"selector": "#b", "score": 1.0,
                             "first_seen": "2026-06-15T00:00:00Z"},
        "link:Logout":      {"selector": "#o", "score": 1.0,
                             "first_seen": "2026-06-15T00:00:00Z"},
    }}))
    ws.pages_path.write_text("# Pages\n\n## login\n- url: x\n\n## inventory\n- url: y\n")
    edir = ws.brain_dir / "exploration"
    edir.mkdir()
    (edir / "exp-login-x.md").write_text("kind: login\n")
    need = MemoryGate(ws).assess(
        Charter(raw="login", kind="login", target_url="https://x"))
    assert need.skip is True
    assert need.proceed_to == "plan"
    assert need.coverage.score >= 0.8
    print(f"✓ E2 rich memory → skip "
          f"(score={need.coverage.score})")


def test_e3_memory_gate_medium():
    ws = _mock_ws(tempfile.mkdtemp())
    ws.selectors_path.write_text(json.dumps({"selectors": {
        "textbox:Username": {"selector": "#u", "score": 1.0,
                             "first_seen": "2026-06-15T00:00:00Z"},
        "textbox:Password": {"selector": "#p", "score": 1.0,
                             "first_seen": "2026-06-15T00:00:00Z"},
    }}))
    need = MemoryGate(ws).assess(
        Charter(raw="login", kind="login", target_url="https://x"))
    # Two of four selectors → score around 0.45*0.5=0.22, gaps reported
    assert need.skip is False
    assert "selectors" in need.coverage.gaps or "pages" in need.coverage.gaps
    print(f"✓ E3 medium memory → score={need.coverage.score} "
          f"gaps={need.coverage.gaps}")


def test_e4_login_strategy_phases():
    strat = get_strategy("login")
    charter = Charter(raw="login", kind="login",
                      target_url="https://x", credentials_id="cred-1")
    snap = Snapshot(url="https://x", title="Login", elements=[
        ElementRef("r1", "textbox", "Username", "#user",
                   attrs={"id": "user", "type": "text"}),
        ElementRef("r2", "textbox", "Password", "#pass",
                   attrs={"id": "pass", "type": "password"}),
        ElementRef("r3", "button", "Login", "#btn"),
    ])
    hist = []
    expected_kinds = ["fill", "fill", "click", "fill", "fill", "click", "stop"]
    for i, exp in enumerate(expected_kinds):
        a = strat.next_action(charter, snap, hist)
        assert a.kind == exp, f"step {i}: want {exp}, got {a.kind}"
        hist.append(ExplorationStep(
            index=i, snapshot_before=snap, action=a, snapshot_after=snap,
        ))
    print("✓ E4 login strategy 7-phase state machine")


def test_e5_explorer_happy_path():
    drv = MockDriver()
    loop = ExplorerLoop(
        browser_factory=make_factory(drv),
        credential_resolver=make_cred_resolver("standard_user",
                                               "secret_sauce"),
    )
    charter = Charter(
        raw="login", kind="login",
        target_url="https://www.saucedemo.com",
        credentials_id="saucedemo-std", max_steps=10,
    )
    report = loop.run(charter)
    assert report.status == "completed", \
        f"want completed, got {report.status} (error={report.error})"
    notes_flat = [n for s in report.steps for n in s.notes]
    assert "LOGIN_SUCCESS" in notes_flat
    assert any("inventory" in p for p in report.pages_discovered), \
        report.pages_discovered
    print(f"✓ E5 saucedemo happy path (status={report.status}, "
          f"steps={len(report.steps)}, "
          f"pages={len(report.pages_discovered)})")


def test_e6_wrong_creds_signal():
    drv = MockDriver()
    loop = ExplorerLoop(
        browser_factory=make_factory(drv),
        # B6 (v1.1.1): use truly wrong creds so MockDriver renders
        # the [data-test=error] element. Pre-B6 the test passed by
        # accident because the heuristic flagged success-page element
        # names containing "Invalid"-like substrings.
        credential_resolver=make_cred_resolver("wrong_user",
                                               "wrong_pass"),
    )
    report = loop.run(Charter(
        raw="login", kind="login",
        target_url="https://www.saucedemo.com",
        credentials_id="saucedemo-std", max_steps=10,
    ))
    notes_flat = [n for s in report.steps for n in s.notes]
    assert "LOGIN_ERROR_VISIBLE" in notes_flat, notes_flat
    print("✓ E6 wrong-creds path captures LOGIN_ERROR_VISIBLE")


def test_e7_blacklist_silent_skip():
    bl = BlacklistGuard()
    d = bl.check(Action(kind="click", target_ref="r1"),
                 ElementRef("r1", "button", "Delete Account"))
    assert d.allow is False
    assert "delete" in d.reason.lower()

    # Also test through evaluate_all
    d2 = evaluate_all(Action(kind="click", target_ref="r2"),
                      ElementRef("r2", "button", "Cancel Subscription"),
                      [bl])
    assert d2.allow is False and d2.guard == "blacklist"
    print("✓ E7 BlacklistGuard silently skips destructive actions")


def test_e8_already_done_prevents_loop():
    g = AlreadyDoneGuard()
    a = Action(kind="click", target_ref="r1")
    g.record(a)
    d = g.check(a, None)
    assert d.allow is False
    print("✓ E8 AlreadyDoneGuard prevents loops")


def test_e9_origin_guard():
    g = OriginGuard(["https://www.saucedemo.com"])
    d = g.check(Action(kind="navigate",
                       value="https://evil.example.com/x"), None)
    assert d.allow is False
    d2 = g.check(Action(kind="navigate",
                        value="https://www.saucedemo.com/inventory"), None)
    assert d2.allow is True
    d3 = g.check(Action(kind="navigate", value="/path"), None)
    assert d3.allow is True
    print("✓ E9 OriginGuard blocks cross-origin navigation")


def test_e10_read_only_mode():
    drv = MockDriver()
    loop = ExplorerLoop(
        browser_factory=make_factory(drv),
        credential_resolver=make_cred_resolver("standard_user",
                                               "secret_sauce"),
    )
    report = loop.run(Charter(
        raw="login", kind="login",
        target_url="https://www.saucedemo.com",
        credentials_id="saucedemo-std", max_steps=10,
        read_only=True,
    ))
    # In read-only mode, no fill/click should have happened.
    fill_clicks = [c for c in drv.method_calls
                   if c.startswith(("fill:", "click:"))]
    assert fill_clicks == [], fill_clicks
    # But navigate + snapshot still allowed
    assert any(c.startswith("goto:") for c in drv.method_calls)
    print(f"✓ E10 read_only=True blocks writes "
          f"(method_calls={len(drv.method_calls)})")


def test_e11_no_form_stops_cleanly():
    """If snapshot has no password field, strategy returns stop and
    loop ends with completed status, not error."""
    class NoFormDriver(MockDriver):
        LOGIN_ELEMENTS = [
            {"role": "heading", "name": "Welcome", "selector": "h1",
             "text": "Welcome", "attrs": {}},
        ]
    drv = NoFormDriver()
    loop = ExplorerLoop(
        browser_factory=make_factory(drv),
        credential_resolver=make_cred_resolver("u", "p"),
    )
    report = loop.run(Charter(
        raw="login", kind="login",
        target_url="https://example.com",
        credentials_id="x", max_steps=5,
    ))
    assert report.status == "completed"
    assert any("No login form detected" in (s.action.rationale or "")
               for s in report.steps), \
        [s.action.rationale for s in report.steps]
    print("✓ E11 no-form page → strategy stops cleanly")


def test_e12_report_renders():
    drv = MockDriver()
    loop = ExplorerLoop(
        browser_factory=make_factory(drv),
        credential_resolver=make_cred_resolver("standard_user",
                                               "secret_sauce"),
    )
    report = loop.run(Charter(
        raw="login flow", kind="login",
        target_url="https://www.saucedemo.com",
        credentials_id="saucedemo-std",
    ))
    md = render_report(report)
    assert "# Exploration: login flow" in md
    assert "## Steps" in md
    assert "## Pages discovered" in md
    assert "/inventory" in md or "inventory.html" in md
    assert "---" in md  # front-matter
    print(f"✓ E12 report renders ({len(md)} bytes, "
          f"{len(report.steps)} steps)")


# ---------------------------------------------------------------------------

def main():
    tests = [
        test_e1_memory_gate_empty,
        test_e2_memory_gate_rich,
        test_e3_memory_gate_medium,
        test_e4_login_strategy_phases,
        test_e5_explorer_happy_path,
        test_e6_wrong_creds_signal,
        test_e7_blacklist_silent_skip,
        test_e8_already_done_prevents_loop,
        test_e9_origin_guard,
        test_e10_read_only_mode,
        test_e11_no_form_stops_cleanly,
        test_e12_report_renders,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            failed += 1
            print(f"✗ {t.__name__}: {e}")
            import traceback
            traceback.print_exc()
    print()
    print("=" * 60)
    if failed == 0:
        print(f"All exploration tests passed ({len(tests)}/{len(tests)}) ✅")
        return 0
    print(f"FAILED {failed}/{len(tests)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
