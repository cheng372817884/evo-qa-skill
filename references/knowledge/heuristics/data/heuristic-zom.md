---
id: heuristic-zom
type: heuristic
scope: universal
title: "Zero, One, Many (ZOM)"
summary: "Zero / One / Many — collection size heuristic"
tags: ['data', 'collections']
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

# Zero, One, Many (ZOM)

**Sometimes written as "0, 1, Many"**

For any collection, count, or quantity: test with zero instances, exactly one instance, and many instances. Also test with the maximum number. Catches off-by-one errors, plural/singular handling, and count boundary failures.

*Examples: 0 items in a cart, 1 item, 100 items. 0 search results, 1 result, thousands of results.*

---
