---
id: heuristic-probe-first
type: heuristic
scope: universal
title: "Probe-First (don't guess, look)"
summary: "When the agent has no learned pattern for a page, do a 1-3 second DOM dump and let an LLM decide — cheaper than blind retry loops."
tags: [exploration, llm, selector, methodology]
domains: []
priority: high
confidence: 0.85
verified_runs: 1
failed_runs: 0
last_used_at: 2026-06-18
last_succeeded_at: 2026-06-18
review_state: active
retrieval_weight: 1.0
source_type: derived
source_ref: "Discovered during enterprise app Create-Account flow — 8 manual evaluate() calls saved ~30 click-retry cycles"
decay_history: []
revival_history: []
created_at: 2026-06-18
updated_at: 2026-06-18
---

# Probe-First (don't guess, look)

## The principle

When entering a page the agent has **no learned pattern for**, the
default behavior should be:

1. **Probe** — dump visible inputs, buttons, labels, and stable IDs (3 seconds, one `page.evaluate`).
2. **Decide** — feed that snapshot to an LLM (or human) along with the goal.
3. **Act** — execute the chosen selector.

…not:

1. ~~Try a guessed selector~~
2. ~~Wait for timeout~~
3. ~~Try another guessed selector~~
4. ~~Eventually escalate~~

## Why this matters

In a session against an unfamiliar SPA, blind-guess loops cost real time:

- Each `wait_for_selector` timeout = 5–30 seconds wasted.
- LLM auto-heal step = 1 round-trip (~2-5s) after the timeout.
- 5 wrong guesses in a row = ~3 minutes of nothing.

A **3-second probe** that produces a real menu of choices replaces all
of that with one decisive action.

## The probe payload (recommended shape)

```python
def probe(page) -> dict:
    return page.evaluate("""() => {
      const visible = el => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
      };
      const grab = sel => Array.from(document.querySelectorAll(sel))
        .filter(visible)
        .slice(0, 50)
        .map(el => ({
          id: el.id,
          name: el.getAttribute('name'),
          type: el.tagName.toLowerCase(),
          role: el.getAttribute('role'),
          aria: el.getAttribute('aria-label'),
          text: (el.innerText || el.value || '').slice(0, 80),
        }));
      return {
        title: document.title,
        url: location.href,
        inputs: grab('input, select, textarea'),
        buttons: grab('button, [role=button], a[href]'),
        headings: grab('h1, h2, h3, [role=heading]'),
      };
    }""")
```

## When to probe

- Entering an unfamiliar page (no MemoryGate hit).
- After a popup closes (the form may have new conditional fields).
- When a previously-working selector fails (page may have re-rendered).
- Before any "chained" interaction (don't probe N times in a row for one form).

## When NOT to probe

- Page already in MemoryGate with high confidence.
- A stable ID library already documents the selector.
- Probing during a hot loop (use a learned pattern instead — that's what brain is for).

## Failure mode this avoids

> *"The script tried `text=Submit` for 30 seconds, then `button:has-text('Submit')` for another 30, before finally succeeding with `#submit-btn`. A probe at second one would have shown there are three buttons containing 'Submit' and one of them is hidden."*

This is exactly what burned us on GW's `text=New Account` (multiple ghost
elements with the same text — quirk #8 in the GW PC quirks doc).
