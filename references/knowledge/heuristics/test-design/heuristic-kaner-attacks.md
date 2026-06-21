---
id: heuristic-kaner-attacks
type: heuristic
scope: universal
title: "Cem Kaner's Software Testing Attacks"
summary: "Cem Kaner's structured testing attacks"
tags: ['attacks', 'design']
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

# Cem Kaner's Software Testing Attacks

**By Cem Kaner**

A set of aggressive, targeted testing strategies to probe specific risk areas. Key attacks include:

- **Long Name Attack**: Submit inputs far exceeding expected length limits (255+, 1000+, 10000+ chars).
- **Special Characters Attack**: Submit inputs containing characters with special meaning: `< > & " ' / \ ; ( ) { } [ ] | * ? % # @ !`
- **Boundary Value Attack**: Test exactly at, just below, and just above defined boundary values.
- **Invalid Type Attack**: Submit data of the wrong type where a specific type is expected (text in a number field, number in a date field).
- **Null/Empty Attack**: Submit null, empty string, whitespace-only, zero, or absent values for every input.
- **Overload Attack**: Submit the maximum number of items, records, or parallel operations.
- **Interruption Attack**: Interrupt operations mid-flight: close the browser, kill the network, pull power, switch tabs.
- **Sequence Attack**: Perform operations out of order, skip steps, repeat steps, or reverse a workflow.

---

## Part 4: Data & Input Heuristics — What Values Do You Test?

These heuristics from the **Test Heuristics Cheat Sheet** (Elisabeth Hendrickson, James Lyndsay, Dale Emery) guide what data and inputs to choose.

---
