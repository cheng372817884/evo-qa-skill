---
id: heuristic-fiblots
type: heuristic
scope: universal
title: "FIBLOTS — Model Workloads for Performance Testing"
summary: "Performance test workload modeling"
tags: ['performance', 'load']
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

# FIBLOTS — Model Workloads for Performance Testing

**By Scott Barber**

When choosing what to performance test, prioritise workloads that are:

| Letter | Criterion | Description |
|--------|-----------|-------------|
| **F** | **Frequent** | Transactions that happen most often will have the highest impact on perceived performance. |
| **I** | **Intensive** | Operations that consume the most resources (CPU, memory, I/O, network). |
| **B** | **Business Critical** | Paths that directly drive revenue, compliance, or mission-critical outcomes. |
| **L** | **Legal** | Performance requirements mandated by contract, SLA, or regulation. |
| **O** | **Obvious** | Things that users will notice immediately if slow: page loads, search, login. |
| **T** | **Technically Risky** | Complex operations, integrations with external services, known bottlenecks. |
| **S** | **Stakeholder Mandated** | Explicit performance goals set by product owners, customers, or leadership. |

---
