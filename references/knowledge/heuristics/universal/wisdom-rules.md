---
id: wisdom-rules
type: reference
scope: universal
title: "Wisdom Heuristics — Rules of Thumb"
summary: "Bach/Bolton wisdom quotes (bugs cluster, fresh eyes find failure, etc.)"
tags: ['wisdom', 'exploration', 'philosophy']
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

## Part 11: Wisdom Heuristics — Rules of Thumb

These are informal but powerful mental models experienced testers use.

---

### "Bugs Cluster"
Defects are not randomly distributed. They cluster around areas of complexity, recent change, and poor design. When you find one bug, look harder in the same area — more are usually nearby. *"Find one bug, find ten more."*

---

### "It's All About the Variables"
Every test is defined by the variables it controls and varies. To find more bugs, find more variables and vary them more deliberately. What has never been varied? What combination has never been tried?

---

### "The Narrower the View, the Wider the Ignorance"
Focusing on only one dimension of a system creates blind spots. Rotate your lens regularly: look at the same feature from a user perspective, a data perspective, a platform perspective, and a security perspective.

---

### "Vary Sequences, Configurations, and Data"
The probability of finding a bug increases with the diversity of what you try. Don't repeat the same test in slightly different ways — introduce genuine variety in the sequence of actions, the configuration of the environment, and the values of data.

---

### "Big Bugs Are Often Found by Coincidence"
Not all bugs are found by methodical analysis. Serendipitous discovery during unplanned exploration catches things structured testing misses. Leave room for following hunches.

---

### "Fresh Eyes Find Failure"
A new tester with no context will find bugs that the experienced team has normalised. The curse of knowledge causes testers to stop noticing things they've seen hundreds of times. Bring in new perspectives deliberately.

---

### "Never and Always"
Every system has behaviours that should *never* happen and behaviours that should *always* happen. Identify them explicitly. Then try to violate the "never" and break the "always." These are the most important invariants to test.

---

### "The Goldilocks Problem"
Not just for data: applies to any dimension of a test. The system should handle not too much, not too little, but just the right amount. Applied to: input length, file size, number of users, time allowed, permissions granted.

---

### "Observe the System Under Test as a Whole"
Bugs in complex systems often manifest at the intersection of components, not within them. Watch for unexpected effects on other parts of the system when testing one area: performance impact, shared state, log pollution, side effects.

---

### "Stopping Heuristics"
Know when to stop a line of investigation. Stop when:
- You've run out of new ideas.
- The risk of continuing is lower than the cost.
- You've reached the time budget.
- You've confirmed or disconfirmed the hypothesis you started with.
- You've found enough information to make a decision.

---

