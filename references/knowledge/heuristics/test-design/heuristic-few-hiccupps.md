---
id: heuristic-few-hiccupps
type: heuristic
scope: universal
title: "FEW HICCUPPS"
summary: "Test oracles — how to recognise a problem"
tags: ['oracle', 'exploration', 'design']
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

# FEW HICCUPPS

**By Michael Bolton & James Bach**

The most widely used oracle heuristic in exploratory testing. Each letter represents a consistency criterion. A product may have a problem if it is inconsistent with any of these:

| Letter | Oracle | Description |
|--------|--------|-------------|
| **F** | **Familiar Problems** | Watch for patterns that match bugs you've seen before. If it looks like a familiar failure mode, investigate. This is the *opposite* of consistency — you want the product to be *inconsistent* with known failure patterns. |
| **E** | **Explainability** | The system's behaviour should be explainable to yourself and others. If you cannot articulate *why* the system did what it did, that's a signal worth chasing. |
| **W** | **World** | The product should be consistent with things that exist and are true in the real world. Physical laws, geography, date logic, domain facts. |
| **H** | **History** | The current version should behave consistently with previous versions unless a change was intentional and communicated. Unexplained regressions are bugs. |
| **I** | **Image** | The product should be consistent with the organisation's desired brand, professional standards, and reputation. Broken UI, spelling errors, or embarrassing output are image problems. |
| **C** | **Claims** | The product should do what its documentation, marketing, help text, labels, tooltips, and UI copy say it does. Any claim made about behaviour is a testable oracle. |
| **C** | **Comparable Products** | Compare behaviour against competitors, prior art, or analogous systems. If they all do X and your product does Y, investigate why. |
| **U** | **User Expectations** | The product should meet the reasonable expectations of its intended users, even when not explicitly specified. |
| **P** | **Product** | The product should be internally consistent with itself. The same operation should produce the same result across contexts, screens, and workflows. |
| **P** | **Purpose** | The product should serve the goals it was designed to serve — not just technically comply with specs. |
| **S** | **Standards** | The product should comply with relevant industry standards, accessibility guidelines, API contracts, and coding conventions. |
| **S** | **Statutes** | The product should comply with applicable laws, regulations, and legal requirements (GDPR, accessibility law, financial regulation, etc.). |

**How to apply:** When you observe a behaviour, ask: "Is this inconsistent with History? With Claims? With User Expectations?" Each oracle gives you language to justify a bug report.

---
