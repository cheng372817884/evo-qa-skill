---
id: heuristic-fcc-cuts-vids
type: heuristic
scope: universal
title: "FCC CUTS VIDS"
summary: "Application touring strategies"
tags: ['touring', 'exploration']
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

# FCC CUTS VIDS

**By Michael D. Kelly**

Eleven distinct touring strategies. Run one per session or combine as needed:

| Tour | What You Do |
|------|-------------|
| **Feature Tour** | Move through every visible feature and control. The goal is familiarity — build a map of what exists. |
| **Complexity Tour** | Find the five most complex things in the application. Complexity = risk. Explore deeply. |
| **Claims Tour** | Find every place the product makes a claim about what it does (labels, tooltips, help text, docs, marketing). Test each claim. |
| **Configuration Tour** | Find every way to change settings that the application persists. Toggle, combine, and reset settings. Look for unexpected interactions. |
| **User Tour** | Identify the key user roles or personas. Test the product as each user would use it, following their realistic goals. |
| **Testability Tour** | Explore the application's built-in mechanisms for testing: logging, debug modes, diagnostics, test data generation, feature flags. |
| **Scenario Tour** | Execute realistic end-to-end user scenarios — stories, not just features. Cover the full journey from entry to completion. |
| **Variability Tour** | Find things that can vary and vary them: input values, screen sizes, speeds, concurrency, data sets. Look for where variation breaks things. |
| **Interoperability Tour** | Test how the product interacts with other systems: APIs, plugins, file formats, external services, browsers, OS features. |
| **Data Tour** | Follow the data. Trace inputs to outputs, storage, and transmission. Look for where data is transformed, truncated, lost, or corrupted. |
| **Structure Tour** | Explore the underlying structure: file system, database schema, API endpoints, configuration files, logs. |

---
