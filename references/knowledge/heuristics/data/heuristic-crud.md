---
id: heuristic-crud
type: heuristic
scope: universal
title: "CRUD"
summary: "Create / Read / Update / Delete — data lifecycle"
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

# CRUD

Create, Read, Update, Delete.

The four fundamental data operations. For any data entity in the system, test all four operations and verify data integrity at each step. Combine with other heuristics:

- *CRUD + Zero-One-Many*: Create 0, 1, many records; Delete a record that has 0, 1, many children.
- *CRUD + Position*: Update the first item, a middle item, the last item.
- *CRUD + Goldilocks*: Create with too-large, too-small, and valid values.

---
