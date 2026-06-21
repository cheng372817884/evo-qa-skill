---
id: heuristic-crud-dependencies
type: heuristic
scope: universal
title: "CRUD + Dependencies"
summary: "CRUD with cross-entity dependencies"
tags: ['data', 'lifecycle']
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

# CRUD + Dependencies

Identify "has-a" relationships (Customer has Invoices; Invoice has Line Items). Apply CRUD and count heuristics across parent-child relationships. Delete a parent with no children, one child, and many children. Create a child before creating the parent.

---
