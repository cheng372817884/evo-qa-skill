---
id: heuristic-multi-match-warning
type: heuristic
scope: universal
title: "Multi-Match Warning (one selector, many elements = bad)"
summary: "Any selector that resolves to more than one visible element is a smell. Treat it as a warning and prefer a stable, scoped alternative before clicking."
tags: [selector, safety, methodology]
domains: []
priority: high
confidence: 0.9
verified_runs: 2
failed_runs: 0
last_used_at: 2026-06-18
last_succeeded_at: 2026-06-18
review_state: active
retrieval_weight: 1.0
source_type: derived
source_ref: "Enterprise app — text='New Account' resolves to 2-3 hidden + 1 visible, click hits the wrong one ~40% of the time"
decay_history: []
revival_history: []
created_at: 2026-06-18
updated_at: 2026-06-18
---

# Multi-Match Warning

## The principle

If a selector matches **more than one element** on the page, it is
ambiguous by definition. Playwright's first-match heuristic *will*
sometimes pick a hidden ghost, a stale duplicate, or a non-interactive
copy. Even worse — you won't see this fail consistently, just
*sometimes*.

**Rule: any time `count() > 1`, escalate.**

## Detection (one line)

```python
def safe_click(page, selector, *, scope=None):
    loc = (scope or page).locator(selector)
    n = loc.count()
    if n == 0:
        raise NoMatch(selector)
    if n > 1:
        # Escalate: find a more specific selector
        raise AmbiguousSelector(selector, count=n)
    loc.first.click()
```

## Escalation ladder (try in order)

When ambiguity is detected, try each fallback in turn:

1. **Stable ID** — does the target have an `id`? Use it directly.
2. **Stable name attribute** — `[name="…"]` is almost always unique.
3. **ARIA label scoped under a parent** — `parent.get_by_role("button", name="X")`.
4. **Text scoped under a stable parent** — `parent.get_by_text("X")` (parent must be `#stable-id`).
5. **Visible filter** — `page.locator(sel).filter(has_text="…").locator(":visible")`.
6. **Index** — only if you've verified it's stable; brittle.

Bare text and `:has-text` selectors should never get past step 1
in production code.

## Why first-match is dangerous

Frameworks like GW, ServiceNow, and many "enterprise SPAs" keep hidden
duplicates of components for state caching, pre-loading, or A/B
variants. These elements:

- Are in the DOM
- May be selectable
- Are not visible
- Will not respond to a real click (or worse, will respond invisibly)

Playwright's default selector engine doesn't care that one is hidden;
it returns matches in document order. The hidden ghost often comes
first.

## How to surface this in tooling

A QA agent's selector engine should:

- Pre-flight every selector with `count()`.
- Log a **WARNING** event any time `count > 1`, even if the action succeeds.
- Persist that warning into the run's CTRF report so reviewers can
  see "this test is one DOM change away from flaking".

This makes flakiness visible *before* it becomes a 2am pager.
