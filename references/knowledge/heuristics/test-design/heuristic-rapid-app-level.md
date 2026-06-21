---
id: heuristic-rapid-app-level
type: heuristic
scope: universal
title: "Rapid Application-Level Heuristics"
summary: "Security, performance, accessibility, i18n, concurrency quick checks"
tags: ['non-functional', 'rapid', 'design']
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

## Part 13: Rapid Application-Level Heuristics

Quick questions to ask about any area of the system:

### Security
- Can a user access data or functionality they shouldn't?
- What happens with direct URL manipulation?
- What happens with crafted API requests (bypassing UI validation)?
- Are session tokens properly invalidated on logout?
- Is sensitive data exposed in URLs, logs, error messages, or browser history?
- Are file uploads validated on the server side?

### Performance
- How does response time change as data volume increases?
- What happens at 10x, 100x the expected load?
- Are there memory leaks visible over time?
- Does the UI remain responsive while background operations run?

### Accessibility
- Is the app usable with keyboard only (no mouse)?
- Does it work with a screen reader?
- Are colour contrast ratios sufficient?
- Do form fields have associated labels?
- Are error messages announced to assistive technology?

### Internationalisation
- Does the UI break with right-to-left languages?
- Do date, time, number, and currency formats respect locale?
- Is translated text correctly accommodated in UI layouts (text expansion)?
- Are non-ASCII characters stored and retrieved correctly?

### Concurrency & State
- What happens when two users perform the same operation simultaneously?
- What happens when the same user opens two tabs?
- Is state correctly isolated between sessions?
- Does the system handle stale reads gracefully?

---

