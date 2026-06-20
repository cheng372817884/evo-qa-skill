---
id: heuristic-slime
type: heuristic
scope: universal
title: "SLIME — Ordering Test Tasks"
summary: "Ordering test tasks"
tags: ['prioritisation']
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

# SLIME — Ordering Test Tasks

**By Adam Goucher**

A prioritisation heuristic for where to focus testing first:

| Letter | Focus | Rationale |
|--------|-------|-----------|
| **S** | **Security** | Security bugs have the highest potential for harm and embarrassment. Test it first. |
| **L** | **Languages** | Localisation and internationalisation bugs are often found late and are expensive to fix. |
| **I** | **Requirements** | Verify requirements are met before exploring edge cases. |
| **M** | **Measurement** | Test analytics, metrics, logging, and monitoring — these are often forgotten. |
| **E** | **Existing** | Regression: ensure existing functionality still works before testing new functionality. |

---

## Part 11: Wisdom Heuristics — Rules of Thumb

These are informal but powerful mental models experienced testers use.

---
