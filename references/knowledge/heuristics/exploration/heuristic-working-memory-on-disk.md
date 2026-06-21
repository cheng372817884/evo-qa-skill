---
id: heuristic-working-memory-on-disk
type: heuristic
scope: universal
title: "Working Memory on Disk (don't trust the context window)"
summary: "For multi-step agentic work, the context window is RAM (volatile, capped) and the filesystem is disk (persistent, unlimited). Anything important — plans, findings, progress — must be written to files, not held in conversation."
tags: [methodology, persistence, planning, agent-memory]
domains: []
priority: high
confidence: 0.9
verified_runs: 1
failed_runs: 0
last_used_at: 2026-06-19
last_succeeded_at: 2026-06-19
review_state: active
retrieval_weight: 1.0
source_type: imported
source_ref: "Inspired by 'planning-with-files' by Othman Adi (MIT, github.com/OthmanAdi/planning-with-files). Methodology adapted; no code copied."
decay_history: []
revival_history: []
created_at: 2026-06-19
updated_at: 2026-06-19
---

# Working Memory on Disk

> **Attribution:** the methodology in this file (three-file plan, 2-action
> rule, 3-strike protocol, 5-question reboot, continue-after-completion)
> originates from [planning-with-files](https://github.com/OthmanAdi/planning-with-files)
> by Othman Adi (MIT-licensed). It is summarized and adapted here for QA
> agent workflows; no code is copied. Cite the upstream when introducing
> these techniques to a team.

## The principle

```
Context Window = RAM (volatile, capped at ~200K tokens)
Filesystem      = Disk (persistent, unlimited)

→ Anything important gets written to disk.
```

A test case worth running is worth resuming. A finding worth observing
is worth keeping. The conversation transcript is *not* a reliable record
of either.

## The three files (one per case run)

For any case that takes > 5 tool calls, three markdown files form the
agent's persistent working memory:

| File | Purpose | Update cadence |
|---|---|---|
| `case_plan.md` | Phases, decisions, error table | After each phase |
| `findings.md` | Selectors, bug leads, UI quirks | After each significant discovery |
| `progress.md` | Chronological session log | Throughout session |

These are the **planning layer** for the agent.
They sit alongside (not instead of) the **data layer** (`result.ctrf.json`)
and the **view layer** (`report.html`).

## The 2-Action Rule

> *After every two `snapshot()`, screenshot, or browser-exploration
> operations, immediately write the takeaways to `findings.md`.*

Why: multimodal output (DOM dumps, screenshots, page text) is bulky
and ephemeral. Each new tool call pushes the previous one further back
in context. By the third snapshot, the first one's specific findings
are at risk.

The fix is mechanical: every two probes, pause and write.

```
1. snapshot(page A)
2. snapshot(page B)
3. ✋ STOP — append to findings.md what we learned about A and B
4. snapshot(page C)
...
```

## The 3-Strike Error Protocol

When an action fails, escalate the *kind* of fix on each retry:

```
ATTEMPT 1 — diagnose & fix
  Read the error. Identify root cause. Apply targeted fix.

ATTEMPT 2 — alternative approach
  Same error means the cause was misdiagnosed.
  Different tool. Different selector. Different abstraction.
  NEVER repeat the exact same failing action.

ATTEMPT 3 — broader rethink
  Question the assumption that made you start this path.
  Search for solutions outside the current code/page.
  Consider amending the case_plan.

After 3 — escalate to the user
  Explain what you tried, share specific errors, ask for guidance.
```

The discipline is: **the third attempt must be qualitatively different
from the first two**, not the same idea with a tweak.

## Read Before Decide / Update After Act

Two cheap habits that prevent ~80% of context-loss failures:

- **Read before deciding.** Before any major decision (next phase,
  architecture pick, escalation), re-read the relevant plan/findings
  file. The act of re-reading drags the goal back into your attention
  window.
- **Update after acting.** After completing any phase, update its
  status (`pending → in_progress → complete`), log files touched,
  and append errors encountered. Do this *before* moving on.

## The 5-Question Reboot Test

If the agent (you) can answer all five, context is solid:

| Question | Source |
|---|---|
| Where am I? | Current phase in `case_plan.md` |
| Where am I going? | Remaining phases |
| What's the goal? | Goal statement at top of `case_plan.md` |
| What have I learned? | `findings.md` |
| What have I done? | `progress.md` |

If any answer is "I'm not sure" or "let me re-read everything" — the
plan files are out of date or the agent skipped *Update After Act*.
Fix that *before* taking any new action.

## Continue After Completion

When the user requests additional work after all phases are marked
complete, **do not start a new run from scratch**. Append.

```
case_plan.md
  ## Phases
  ### Phase 1 ... complete
  ### Phase 2 ... complete
  ### Phase 3 ... complete
  ### Phase 4 (added 2026-06-19): … in_progress    ← appended
```

The plan grows. The findings carry over. The progress log gets a
new session entry. This preserves continuity and prevents
re-litigating decisions made in prior phases.

## Resume Across Sessions

The whole point of writing memory to disk is that **the next session
can pick up where this one left off**. Treat session boundaries as
expected events, not errors.

### The resume protocol

When opening a run started in a previous session:

1. **Locate.** Find the run folder: `_runs/<run-id>/`.
2. **Read all three files first** — `case_plan.md`, `findings.md`,
   `progress.md` — before any other action. Do not start probing
   the page until you've reconstructed your own state from disk.
3. **Run the 5-Question Reboot Test** out loud:
   - Where am I? → `case_plan.md` *Current Phase*
   - Where am I going? → remaining phases
   - What's the goal? → `case_plan.md` *Goal* line
   - What have I learned? → `findings.md`
   - What have I done? → `progress.md` session log
4. **Verify before acting.** Specifically:
   - If the run is browser-based: re-login (cookies likely expired).
   - Re-probe the current page; compare against the last snapshot
     described in `findings.md`. Are we still where we think we are?
   - If reality has drifted from the plan: update the plan
     *first*, then act. Don't act on a stale plan.
5. **Then take the next step.**

### What resume is, and is not

| What it IS | What it is NOT |
|---|---|
| A reliable way to recover *the agent's intent* | A way to recover *the system's state* |
| A fast way to skip re-discovering selectors | A magic flag that re-establishes a logged-in browser |
| A continuity contract between sessions | A determinism guarantee — different model = different choices |
| A debug aid: "here's what I was trying" | A snapshot of the SUT — for that, query the SUT |

### When resume is dangerous

- The plan files have not been updated for hours/days. Mtime is a
  signal: anything older than your environment's session lifetime
  (cookie expiry, sandbox refresh) needs *reverification*, not
  *resume*.
- The system-under-test had a deployment or data refresh between
  sessions. The plan describes a system that no longer exists.
- A different agent (different LLM, different operator) ran in
  between. They may have advanced the state without updating the
  plan files.

In all three cases: **read the plan to understand the intent, then
treat the system as fresh** — re-probe, re-verify, possibly amend
the plan. Don't blindly resume.

### Resume vs. restart — a decision rubric

| Situation | Resume | Restart |
|---|---|---|
| Same day, context window filled | ✅ resume | |
| Overnight gap, sandbox is stable | ✅ resume + reverify | |
| Sandbox refreshed since last session | | ✅ restart |
| Plan files corrupted or empty | | ✅ restart |
| User asks to "rerun from scratch" | | ✅ restart |
| Different agent ran in between | ⚠️  resume + full reverify | or restart |

When in doubt, **restart is cheaper than wrong-resume**. A 5-minute
restart beats a 30-minute debug of stale assumptions.

## When to apply

- Multi-step QA cases (3+ steps).
- Any case spanning a context-window boundary (compaction, /clear, restart).
- Exploration sessions where the goal is to *discover* the right test.
- Any task with > 5 tool calls.

## When to skip

- Single-action tasks ("verify the button is disabled").
- Quick lookups against an already-cached brain pattern.
- Sub-second probes inside an already-running phase.

## Anti-patterns

| Don't | Do instead |
|---|---|
| Use ephemeral todo lists in conversation | Write `case_plan.md` |
| State a goal once and never re-read it | Read before deciding |
| Hide a failure and silently retry | Log the error, change the approach |
| Cram screenshots into context | Caption them in `findings.md`, drop the bytes |
| Start a fresh run for additional work | Append a phase to the existing plan |
| Repeat a failed action with a small tweak | Mutate the *kind* of approach (3-strike) |
