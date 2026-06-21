---
id: heuristic-failure
type: heuristic
scope: universal
title: "FAILURE"
summary: "Error handling evaluation"
tags: ['error-handling', 'design']
domains: []
priority: high
confidence: 1.0
verified_runs: 0
failed_runs: 0
last_used_at: null
last_succeeded_at: null
review_state: active
retrieval_weight: 1.0
source_type: imported
source_ref: "github.com/danashby/Exploratory-Testing-Skill (MIT)"
decay_history: []
revival_history: []
created_at: 2026-06-17
updated_at: 2026-06-17
---

# FAILURE

**By Ben Simo**

Use this to evaluate the quality of error handling whenever an error state is encountered:

| Letter | Check | Description |
|--------|-------|-------------|
| **F** | **Functional** | Does the system continue to function correctly after the error? Or is it stuck? |
| **A** | **Appropriate** | Is the error message appropriate for the audience? Developers, end users, and admins need different messages. |
| **I** | **Impact** | What is the actual impact of the error on the user, the system, and the data? Has anything been corrupted or lost? |
| **L** | **Log** | Is the error logged with enough detail to diagnose it? Is sensitive information excluded from logs? |
| **U** | **UI** | Does the UI communicate the error clearly? Is it visible, readable, and non-misleading? |
| **R** | **Recovery** | Can the user or system recover from the error? Is recovery automatic, guided, or manual? |
| **E** | **Emotions** | How does the error make the user feel? Confused? Alarmed? Reassured? Does the tone fit the context? |

---

## Part 8: Bug Advocacy & Reporting Heuristics

---
