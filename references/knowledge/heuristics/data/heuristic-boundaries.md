---
id: heuristic-boundaries
type: heuristic
scope: universal
title: "Boundaries"
summary: "Numeric and string boundary testing"
tags: ['data', 'boundaries']
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

# Boundaries

Test the exact boundary value, one below, and one above. For numeric ranges, string lengths, date ranges, file sizes, and any defined limit. Boundary bugs are extremely common.

*Examples: A field that accepts 1–100 characters — test 0, 1, 50, 99, 100, 101. A date range that starts on 1 Jan — test 31 Dec, 1 Jan, 2 Jan.*

---
