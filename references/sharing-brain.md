# Sharing your Evo QA brain

Once you've used Evo QA on a project for a while, you accumulate
real value — selectors that worked, pages your team cares about,
contradictions you've already chased, heuristics you've tuned. This
guide explains how to share that value.

---

## Three export formats

| Format | What it is | Best for |
|--------|------------|----------|
| `mem0`  | Stock-`mem0`-compatible JSON | Bringing your knowledge to another agent (Mem0, Letta, anything that speaks the mem0 protocol) |
| `ctrf`  | Bundle of every `result.ctrf.json` across runs | CI dashboards, regulatory audit, post-mortem analysis |
| `json`  | Raw dump of the brain YAMLs | Archival, custom pipelines, debugging |

```bash
python -m evo_qa.core.cli export <project> --format mem0
python -m evo_qa.core.cli export <project> --format ctrf
python -m evo_qa.core.cli export <project> --format json
```

The output lands at `<workspace>/exports/<format>/` unless you pass
`--out <path>`.

---

## mem0 export — what's actually in it

`memories.json` is an array. Each entry looks like:

```json
{
  "memory": "[page] Login (https://app.example.com/login)",
  "agent_id": "evo-qa",
  "user_id": "myproj",
  "metadata": {
    "kind": "page",
    "source_id": "page-1",
    "state": "active",
    "tags": ["login", "auth"],
    "evidence": ["run-abc123"],
    "skill": "evo-qa"
  },
  "created_at": "2026-06-18T10:00:00Z"
}
```

What we translate, today:

| Brain kind | Memory text | Notes |
|------------|-------------|-------|
| page          | `[page] <title> (<url>)` | One per known page |
| transition    | `[transition] <from> -> <to> via <action>` | Navigation graph |
| observation   | `[observation] <claim>` | LLM-derived facts |
| question      | `[question] <text>` | Open issues |
| contradiction | `[contradiction] <left> vs <right>` | Disagreements with prior knowledge |

**Not exported (yet):**

- Heuristics (they're already shared with the skill itself —
  `references/knowledge/heuristics/`)
- Selectors (project-specific, leak too easily across teams)
- Credentials (never)

---

## How to import into mem0

```python
from mem0 import Memory
import json

m = Memory()
for entry in json.load(open("memories.json")):
    m.add(
        entry["memory"],
        user_id=entry["user_id"],
        agent_id=entry["agent_id"],
        metadata=entry["metadata"],
    )
```

Or with the Mem0 CLI (when available):

```bash
mem0 import memories.json --agent-id evo-qa
```

The README produced alongside `memories.json` always carries the
import snippet against the version of mem0 we tested with.

---

## Sharing across teammates

The cleanest contract:

1. Person A: `cli export myproj --format mem0` → ships `memories.json`.
2. Person B: drops it into their workspace, points their agent at it,
   gets the cumulative knowledge.

**What gets lost in translation:**

- Mem0 doesn't preserve our state machine (`active → stale → deprecated
  → archived`). Everything imported lands as `active`. Use the metadata
  `state` field if you need to filter post-import.
- Mem0 doesn't preserve our `provenance.evidence` chain in a
  first-class way. We stuff it into `metadata.evidence` so downstream
  callers can reconstruct it.

**What's preserved correctly:**

- The natural-language memory string (what mem0 actually retrieves on)
- Tags
- Project / agent identity
- Creation timestamps

---

## CTRF bundle export

```bash
python -m evo_qa.core.cli export myproj --format ctrf
```

Produces:

```
exports/ctrf/
├── index.json                          # one row per run
├── test-login/
│   ├── run-1.ctrf.json
│   └── run-2.ctrf.json
├── test-checkout/
│   └── run-3.ctrf.json
└── ...
```

Drop the whole directory into a CTRF-aware dashboard
([CTRF Reports](https://ctrf.io)) and you get a unified history of
every Evo QA run for that project.

---

## Privacy reminders

Never put these in any export:

- Passwords (the credential store is **not** included by default).
- Tokens / API keys appearing inside test scripts (scrub before sharing).
- Internal URLs that violate your team's data-handling policy.

The skill never embeds passwords into brain entries, run records,
reports, or generated test code in the first place — but you should
still eyeball the export before forwarding it to a third party.
