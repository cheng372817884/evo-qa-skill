---
id: pitfall-virtualized-dropdown
type: pitfall
scope: universal
title: "Virtualized / custom dropdowns need 5-tier fallback"
summary: "Custom comboboxes (react-select, ant-design, cdk-virtual-scroll, GW LV) don't render all options — naive click fails. Use the select_option_smart atom."
tags: [dropdown, virtualization, react-select, ant-design, listbox, combobox, critical]
domains: [universal]
priority: high
confidence: 0.92
verified_runs: 1
failed_runs: 0
last_used_at: 2026-06-18
last_succeeded_at: 2026-06-18
review_state: active
retrieval_weight: 1.0
source_type: imported
source_ref: "Playwright issues #5212, #14734, #9073, #17042; community-validated patterns"
decay_history: []
revival_history: []
created_at: 2026-06-18
updated_at: 2026-06-18
---

# Virtualized / Custom Dropdowns — Why Naive Click Fails

## Smell

You see one or more of these:

- "element not visible" or "not attached" on what *looks* like a normal option
- Test passes locally but fails in CI — smaller viewport means **more** virtualization
- Dropdown inside a modal scrolls the **modal** up and down forever (Playwright #9073)
- `count()` returns a small number (e.g. 10) when the data has hundreds of rows
- `selectOption()` raises `Element is not a <select> element`

## Why

Most modern UI frameworks build dropdowns out of `<div role="listbox">` + `<div role="option">`, not native `<select>`. Many also **virtualize**: only ~10 rows are in the DOM at any time; scrolling reveals more. Two failure modes:

1. **Wrong API** — `selectOption()` only works on native `<select>`.
2. **Option not rendered** — the row you want isn't in the DOM yet, so any selector targeting it fails.

`scrollIntoViewIfNeeded()` on the (non-existent) target then asks the browser to scroll a parent container — often the **modal or page**, not the dropdown — into view. That's the source of the infinite up/down scroll bug (#9073).

## The 5-Tier Fallback (in reliability order)

| Tier | Technique | When to use |
|---|---|---|
| 1 | `selectOption(label=...)` | element is a real `<select>` |
| 2 | type-to-filter: `fill()` on combobox → click first match | trigger is `<input>` or `role=combobox\|searchbox` |
| 3 | check `count() > 0` → `scrollIntoViewIfNeeded()` → `click()` | option already in DOM (non-virtualized) |
| 4 | scroll **container only** (not page!), retry tier 3 each loop | virtualized list (cdk-virtual-scroll, react-window) |
| 5 | open dropdown → `keyboard.press("ArrowDown")` × N → check focused → `Enter` | nothing else worked; ARIA listbox supports it |

## In This Skill — Use the Atom

Don't write this by hand. Use `select_option_smart` — it implements all 5 tiers automatically:

```python
from evo_qa.core.atoms import select_option_smart

select_option_smart(
    "#country-trigger",       # what you click to open the dropdown
    "United Arab Emirates",   # the option's visible text
    dropdown_container=".rc-virtual-list",   # optional, default [role=listbox]
    option_selector='.rc-option:has-text("{value}")',  # optional, {value} placeholder
    max_scrolls=25,           # optional, default 20
    prefer_keyboard=False,    # set True to skip type-to-filter
)
```

The atom returns `extra={"tier": N, "trail": [...]}` so reports show **which tier won**, useful diagnostics for flaky pages.

## Anti-Patterns

```python
# ❌ option.scrollIntoViewIfNeeded() inside a modal — scrolls the modal, not the listbox
await page.locator(".my-option").scrollIntoViewIfNeeded()

# ❌ page.mouse.wheel() — fires at cursor position, often misses the listbox
await page.mouse.wheel(0, 500)

# ❌ Trusting count() on virtualized lists — only renders ~10 items at a time
expect(page.locator("[role=option]")).to_have_count(500)   # will fail
```

```python
# ✅ Scroll the listbox container itself
await page.locator("[role=listbox]").evaluate(
    "el => { el.scrollTop += el.clientHeight * 0.8 }"
)
```

## References

- [microsoft/playwright#5212](https://github.com/microsoft/playwright/issues/5212) — react-select
- [microsoft/playwright#14734](https://github.com/microsoft/playwright/issues/14734) — ant-design
- [microsoft/playwright#17042](https://github.com/microsoft/playwright/issues/17042) — virtualized rendering question
- [microsoft/playwright#9073](https://github.com/microsoft/playwright/issues/9073) — modal + dropdown scroll loop
- [Playwright docs — Scrolling](https://playwright.dev/docs/input#scrolling)

## Project-Specific Hints

- **react-select** — option selector `.css-...-option:has-text("{value}")`; or use type-to-filter (Tier 2 wins)
- **ant-design v4 select** — container `.ant-select-dropdown`, option `.ant-select-item-option:has-text("{value}")`
