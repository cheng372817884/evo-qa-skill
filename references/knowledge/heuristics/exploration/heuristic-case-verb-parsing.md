---
id: heuristic-case-verb-parsing
type: heuristic
scope: universal
title: "Case Verb Parsing (the first verb is structural)"
summary: "The first verb of a test case title (Create / Edit / Search / Submit / Delete) determines the entry-point and entire flow shape — parse it before writing selectors."
tags: [test-design, parsing, methodology]
domains: []
priority: high
confidence: 0.9
verified_runs: 1
failed_runs: 1
last_used_at: 2026-06-18
last_succeeded_at: 2026-06-18
review_state: active
retrieval_weight: 1.0
source_type: derived
source_ref: "Cost: one wasted exploration loop where 'Create a Company Account' was misread as 'use the existing account named Illinois'"
decay_history: []
revival_history: []
created_at: 2026-06-18
updated_at: 2026-06-18
---

# Case Verb Parsing

## The principle

Every test case title starts with a **verb** that is structural, not
stylistic. The verb determines:

- Entry point in the UI
- Whether you need pre-existing data
- What the success signal looks like

If you skip parsing the verb, you may write a perfectly correct script
that solves the wrong problem.

## Common verbs and their entry-point shapes

| Verb | Entry point pattern | Pre-condition | Success signal |
|---|---|---|---|
| **Create** | "New X" action menu / "+" button | None (clean slate) | New entity ID returned |
| **Edit / Update** | Open existing X → field → save | Existing X | Updated values persist |
| **Search / Find** | Search section → filter → submit | Some X must exist | Result row visible |
| **View / Read** | Direct navigation → link/ID | The X must exist | Detail page loaded |
| **Submit** | Workflow start (often nested under another entity) | Parent entity exists | Workflow advanced state |
| **Delete / Remove / Withdraw** | Open X → action menu → confirm | The X must exist | X gone or marked withdrawn |
| **Verify / Validate** | Read + assert | All inputs exist | Assertion passes |

## The mis-parse trap

Ambiguous titles often hide a different verb:

- *"Create a Company Account for Illinois Insurance"* — **verb is Create**, "Illinois Insurance" is the *name* of the new account, not an existing one to look up.
- *"Add a driver to policy 123"* — verb is **Edit** (on policy 123), not **Create** (in isolation).
- *"Confirm the customer's address"* — verb is **Verify**, no UI write should happen.

When in doubt, ask:
> *"After this case passes, what changed in the system? A new row? A modified row? Just a read?"*

That tells you the verb.

## Recommended parser shape

```python
def parse_case_title(title: str) -> CaseSpec:
    """
    Returns: { verb, primary_entity, qualifiers, names_or_ids }
    """
    # Tokenize, find the first imperative verb
    # Common verbs: create|add|new|make → CREATE
    #               edit|update|change|modify → EDIT
    #               search|find|lookup|locate → SEARCH
    #               view|open|read|show → VIEW
    #               submit|start|initiate → SUBMIT
    #               delete|remove|withdraw|cancel → DELETE
    #               verify|check|validate|assert → VERIFY
    ...
```

## Cheap sanity gate

Before writing a single selector:

```
verb = parse(title)
if script.first_action_verb != verb:
    raise CaseTitleMismatchError(
        f"Title says {verb} but script starts with {script.first_action_verb}"
    )
```

This costs nothing and catches the entire class of "I built a Search
script for a Create case" failures before they touch the browser.
