---
id: heuristic-rcrcrc
type: heuristic
scope: universal
title: "RCRCRC"
summary: "Regression test prioritisation — Recent/Core/Risky/Configuration-sensitive/Repaired/Chronic"
tags: ['regression', 'design']
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

# RCRCRC

**By Karen Johnson**

Use this to identify *what* to regression test when a change is made:

| Letter | Focus | What to Ask |
|--------|-------|-------------|
| **R** | **Recent** | What new features or code were added? New code is more likely to introduce bugs. |
| **C** | **Core** | What essential functionality must always work? What would be catastrophic to break? |
| **R** | **Risky** | What areas of the codebase or product are inherently risky or complex? |
| **C** | **Configuration-Sensitive** | What code depends on environment settings, feature flags, or infrastructure config? |
| **R** | **Repaired** | What bugs were fixed in this release? Bug fixes can introduce new failures nearby. |
| **C** | **Chronic** | What areas perpetually break or have a history of instability? These need watching every time. |

---

## Part 7: Error Handling Heuristics

---
