"""
Reverse-engineer legacy runs into TraceEvents.

Old runs (pre-v1.0) don't carry per-atom traces. We have only:
  - the pytest test file
  - the run record JSON (status, duration, notes, screenshots_dir)

We approximate by parsing the test file and converting Playwright calls
into TraceEvents. This is BEST-EFFORT and the resulting brain entries
are marked with low confidence + a known_unknown noting the source.

We do NOT try to perfectly reconstruct page titles between every step.
We use a small dictionary of known anchors (login -> summary -> form -> ...)
plus a heuristic: every `_shot()` call typically corresponds to a stable
page state.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .extractor import TraceEvent


# Known page-title anchors (calibrated to actual observed titles)
GW_ANCHORS = {
    "01_after_login": "App Name (User Role) My Summary",
    "02_dropdown_open": "App Name (User Role) My Summary",
    "03_new_company_form": "App Name (User Role) New Contact",
    "04_basic_filled":     "App Name (User Role) New Contact",
    "05_address_filled":   "App Name (User Role) New Contact",
    "06_address_type":     "App Name (User Role) New Contact",
    "06_address_type_billing": "App Name (User Role) New Contact",
    "07_after_update":     "App Name (User Role) Contact File Details",
}


# Patterns we recognise — keep tight to avoid false positives.
# Value group can be either a quoted literal OR a data["key"] reference.
# We'll capture the raw text and call sub_data() on it later.
_VAL = r"""(?:['"][^'"]*['"]|data\[['"][^'"]+['"]\])"""

_PATTERNS = [
    # page.fill('selector', 'value' | data["k"])
    (re.compile(rf"""\.fill\(\s*['"]([^'"]+)['"]\s*,\s*({_VAL})"""),
     "fill"),
    # page.select_option('sel', label='Ohio'|data["state"])
    (re.compile(rf"""\.select_option\(\s*['"]([^'"]+)['"]\s*,\s*label\s*=\s*({_VAL})"""),
     "select_label"),
    (re.compile(rf"""\.select_option\(\s*['"]([^'"]+)['"]\s*,\s*({_VAL})"""),
     "select_label"),
    # page.click('sel')
    (re.compile(r"""\.click\(\s*['"]([^'"]+)['"]"""),
     "click"),
    # page.press('sel', 'Enter' | data["k"])
    (re.compile(rf"""\.press\(\s*['"]([^'"]+)['"]\s*,\s*({_VAL})"""),
     "press"),
    # page.goto('url')
    (re.compile(r"""\.goto\(\s*['"]([^'"]+)['"]"""),
     "goto"),
    # _shot(page, '01_after_login') or _shot(page, run_dir, '01_after_login')
    (re.compile(r"""_shot\([^,]+,\s*(?:[^,]+,\s*)?['"]([^'"]+)['"]"""),
     "shot"),
    # _gw_fill(page, 'wrapper_id', 'value' | data["k"])
    (re.compile(rf"""_gw_fill\([^,]+,\s*['"]([^'"]+)['"]\s*,\s*({_VAL})"""),
     "gw_fill"),
    # _gw_select(page, 'wrapper_id', 'label' | data["k"])
    (re.compile(rf"""_gw_select\([^,]+,\s*['"]([^'"]+)['"]\s*,\s*({_VAL})"""),
     "gw_select"),
]


def _strip_quotes(s: str) -> str:
    """Strip surrounding quotes if any. Leave data[...] alone."""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def parse_test_file(path: Path,
                    *,
                    data_substitution: Optional[dict] = None
                    ) -> list[TraceEvent]:
    """Walk a pytest file top-to-bottom, return synthetic TraceEvents.

    `data_substitution`: optional dict to substitute when value looks like
    `data["company"]` etc. Used when reverse-engineering parametrized runs.

    Handles both single-line calls and the multi-line style commonly
    produced by black/ruff formatters:

        _gw_fill(
            page,
            "wrapper-id",
            data["company"],
        )
    """
    text = path.read_text(encoding="utf-8", errors="ignore")

    # Pre-process: collapse multi-line function calls into single lines.
    # Naive but adequate for our test files: when an open-paren has more
    # opens than closes on its line, keep glueing the next line until
    # parens balance.
    flat_lines: list[str] = []
    buf = ""
    depth = 0
    for raw in text.splitlines():
        if buf or depth > 0:
            buf += " " + raw.strip()
        else:
            buf = raw
        depth += buf.count("(") - buf.count(")") - (
            (buf.count("(") if not buf else 0) - depth)
        # Simpler/correct re-compute on the running buffer:
        depth = buf.count("(") - buf.count(")")
        if depth <= 0:
            flat_lines.append(buf)
            buf = ""
            depth = 0

    events: list[TraceEvent] = []
    current_title = ""

    # Helper to substitute data["key"] references using the run's actual data
    def sub_data(value: str) -> str:
        if data_substitution and "data[" in value:
            for k, v in data_substitution.items():
                value = value.replace(f'data["{k}"]', str(v))
                value = value.replace(f"data['{k}']", str(v))
        return value

    for line in flat_lines:
        s = line.strip()
        if s.startswith("#") or not s:
            continue
        for pat, kind in _PATTERNS:
            m = pat.search(line)
            if not m:
                continue

            if kind == "shot":
                anchor = m.group(1)
                title = GW_ANCHORS.get(anchor, "")
                if title:
                    if current_title and current_title != title:
                        # Synthesize a "title transition" event so the
                        # extractor can emit a Transition edge.
                        events.append(TraceEvent(
                            atom="navigate",
                            target="",
                            value="",
                            ok=True,
                            page_title_before=current_title,
                            page_title_after=title,
                            notes=f"reached @ {anchor}",
                        ))
                    current_title = title
                break

            target = m.group(1) if m.lastindex else ""
            value = m.group(2) if (m.lastindex or 0) >= 2 else ""
            value = _strip_quotes(value)

            if kind == "goto":
                ev = TraceEvent(
                    atom="goto", target=target, value="",
                    page_title_before="",
                    page_title_after="App Login",
                )
                current_title = "App Login"
                events.append(ev)
            elif kind == "fill":
                events.append(TraceEvent(
                    atom="fill", target=target, value=sub_data(value),
                    page_title_before=current_title,
                    page_title_after=current_title,
                ))
            elif kind == "gw_fill":
                # Reconstruct the wrapper-id selector pattern
                ev_target = f"#{target} input"
                events.append(TraceEvent(
                    atom="fill", target=ev_target,
                    value=sub_data(value),
                    page_title_before=current_title,
                    page_title_after=current_title,
                    notes="gw wrapper-id pattern",
                ))
            elif kind == "select_label":
                events.append(TraceEvent(
                    atom="select", target=target, value=sub_data(value),
                    page_title_before=current_title,
                    page_title_after=current_title,
                ))
            elif kind == "gw_select":
                ev_target = f"#{target} select"
                events.append(TraceEvent(
                    atom="select", target=ev_target,
                    value=sub_data(value),
                    page_title_before=current_title,
                    page_title_after=current_title,
                    notes="gw wrapper-id select",
                ))
            elif kind == "click":
                events.append(TraceEvent(
                    atom="click", target=target,
                    page_title_before=current_title,
                    page_title_after=current_title,
                ))
            elif kind == "press":
                events.append(TraceEvent(
                    atom="press", target=target, value=sub_data(value),
                    page_title_before=current_title,
                    page_title_after=current_title,
                    notes="key press",
                ))
            break  # one match per line

    return events


__all__ = ["parse_test_file", "GW_ANCHORS"]
