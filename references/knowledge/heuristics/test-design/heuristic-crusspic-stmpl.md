---
id: heuristic-crusspic-stmpl
type: heuristic
scope: universal
title: "CRUSSPIC STMPL"
summary: "Non-functional quality attributes"
tags: ['non-functional', 'quality', 'design']
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

# CRUSSPIC STMPL

**By James Bach (from the Heuristic Test Strategy Model)**

A quality attribute model for non-functional testing. Split into two parts:

**CRUSSPIC — Operational Quality Criteria:**

| Letter | Criterion | Description |
|--------|-----------|-------------|
| **C** | **Capability** | Does it do what it's supposed to do? All intended features present and functional. |
| **R** | **Reliability** | Does it keep working under expected conditions over time? Stable, consistent, no random failures. |
| **U** | **Usability** | Can users figure out how to use it without pain? Learnability, efficiency, error recovery. |
| **S** | **Security** | Is it protected against misuse, unauthorised access, data exposure, and attack vectors? |
| **S** | **Scalability** | Does it cope with increasing load, data volume, or number of users? |
| **P** | **Performance** | Does it respond in acceptable time under normal and peak conditions? |
| **I** | **Installability** | Can it be installed, configured, updated, and uninstalled cleanly across target environments? |
| **C** | **Compatibility** | Does it work correctly alongside other systems, browsers, versions, and platforms? |

**STMPL — Development Quality Criteria:**

| Letter | Criterion | Description |
|--------|-----------|-------------|
| **S** | **Supportability** | Can it be monitored, diagnosed, and supported in production? Logging, alerting, diagnostics. |
| **T** | **Testability** | Can it be tested? Are there hooks, observability, and controllability to enable verification? |
| **M** | **Maintainability** | Can it be changed without high risk? Code quality, modularity, documentation. |
| **P** | **Portability** | Can it be moved to different environments, platforms, or configurations? |
| **L** | **Localisability** | Can it be adapted for different languages, regions, currencies, date formats, and cultural conventions? |

---
