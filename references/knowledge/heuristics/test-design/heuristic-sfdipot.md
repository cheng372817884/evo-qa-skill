---
id: heuristic-sfdipot
type: heuristic
scope: universal
title: "SFDIPOT (San Francisco Depot)"
summary: "Product coverage — Structure, Function, Data, Interfaces, Platform, Operations, Time"
tags: ['coverage', 'design', 'htsm']
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

# SFDIPOT (San Francisco Depot)

**By James Bach**

A product coverage model. Use this to ensure your exploratory session doesn't accidentally ignore entire dimensions of the system. Each letter is a domain to explore:

| Letter | Area | What to Explore |
|--------|------|-----------------|
| **S** | **Structure** | The physical and logical components: files, databases, config files, APIs, code modules, UI elements, third-party libraries. What does the product *consist of*? |
| **F** | **Function** | What the product *does*: features, behaviours, operations, commands, transactions. Explore both the happy path and the edges of each function. |
| **D** | **Data** | Inputs the product accepts, outputs it produces, data it stores and retrieves. Focus on types, ranges, formats, encoding, validation, transformation, and corruption. |
| **I** | **Interfaces** | How the product connects to things outside itself: APIs, databases, file systems, external services, hardware, browsers, OS. Integration points are high-risk. |
| **P** | **Platform** | The environment the product runs in: OS, browser, hardware, network, screen resolution, locale, container, cloud infrastructure. Vary the platform. |
| **O** | **Operations** | How users *use* the product in real-world contexts: workflows, sequences, habits, interruptions, concurrent users, admin operations, scheduled jobs. |
| **T** | **Time** | Time-sensitive behaviours: timeouts, session expiry, scheduled tasks, leap years, daylight saving changes, date/time formatting, race conditions, concurrency, sequencing. |

**Extended version:** Sometimes written as **SFDPOT** (without the I for Interfaces). Karen Johnson added T for Time for mobile testing contexts.

---
