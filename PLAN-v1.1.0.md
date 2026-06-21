# Evo QA — v1.1.0 Implementation Plan

> **Status**: APPROVED by user 2026-06-18
> **Scope**: 4 packages combined → single release
> **Estimated effort**: 33-42h ≈ 5-7 working days
> **Strategy**: One big release, no intermediate versions

---

## 🎯 Why one release (not v1.0.5 + v1.1.0 separately)

User decision: do all of below in a single v1.1.0 release.

Reasoning:
1. agentskills.io directory rename is a breaking change anyway — pay the cost once
2. CTRF integration touches the same `runs/` and `report/` modules as rc1 fixes
3. Less version churn for downstream users
4. We can audit and validate the whole new shape together

---

## 📦 Package overview

| # | Package | Effort | Purpose |
|---|---|---|---|
| **A** | rc1 feedback fixes | 1-3h passive | Bug fixes from Cline real-world testing |
| **B** | CTRF report standardization | 14-16h | Solve "every report looks different" |
| **C** | agentskills.io compliance | 6-8h | Open-standard packaging, broad client support |
| **D** | Knowledge portability (mem0 export) | 3-4h | Answer "share brain with others" |
| **E** | BM25 retrieval index | 3-4h | Fix search quality collapse beyond 5000 entries |
| **F** | README + sharing guide rewrite | 2.5h | User-facing docs |
| **G** | Final tests + audit + release | 2-3h | Quality gate |
| | **Total** | **~33-42h** | |

---

## 📋 Detailed task list (52 items, ordered by dependency)

### Stage 0 — Pre-flight (30min)

- [ ] 0.1 Backup current `evo_qa/` to `evo_qa.v1.0.4-backup/`
- [ ] 0.2 Read latest rc1 feedback if available (`/app/working/exports/`)
- [ ] 0.3 Confirm 46/46 tests still pass on current code
- [ ] 0.4 Create `CHANGELOG.md` v1.1.0 placeholder section

### Stage 1 — agentskills.io directory restructure (Package C, ~3h)

> Do this FIRST — all subsequent file paths depend on the new layout.

- [ ] 1.1 Rename top-level dir: `evo_qa/` → `evo-qa/` (skill dir)
- [ ] 1.2 Keep Python module name `evo_qa` (underscore, Python requirement)
- [ ] 1.3 Move `knowledge/` → `references/knowledge/`
- [ ] 1.4 Move `templates/` → `assets/templates/`
- [ ] 1.5 Move `workspace_init/` → `assets/workspace_init/`
- [ ] 1.6 Move `prompts/` → `references/prompts/`
- [ ] 1.7 Update all path constants in `core/workspace.py`, `core/orchestrator.py`
- [ ] 1.8 Run 46/46 test suite — must still pass
- [ ] 1.9 Add `assets/ctrf.schema.json` (CTRF v1.0 schema offline copy)

### Stage 2 — SKILL.md frontmatter + body update (Package C, ~2h)

- [ ] 2.1 Change `name: evo_qa` → `name: evo-qa`
- [ ] 2.2 Flatten `metadata.copaw.*` → `metadata.copaw-emoji` etc. (string→string)
- [ ] 2.3 Add "When to load which file" directives section:
  - `references/playbooks/explorer-loop.md` — when planning
  - `references/domains/` — when domain-specific knowledge is needed
  - `references/ctrf-spec.md` — when emitting reports
- [ ] 2.4 Add "Reports — STRICT REQUIREMENTS" section (CTRF hard contract)
- [ ] 2.5 Add "Black-box scripts" one-liner (steal from webapp-testing)
- [ ] 2.6 Verify SKILL.md still <500 lines, <5000 tokens

### Stage 3 — CTRF data layer (Package B, ~5h)

- [ ] 3.1 Write `references/ctrf-spec.md` — inline key schema + our extension conventions
- [ ] 3.2 Add `core/reporting/ctrf_emit.py` — emit CTRF-compliant JSON
- [ ] 3.3 Refactor `runs/{id}/result.json` → `result.ctrf.json`
- [ ] 3.4 Add `core/reporting/ctrf_validate.py` — local jsonschema validation
- [ ] 3.5 Add `cli validate-ctrf <run-id>` subcommand
- [ ] 3.6 Audit item 13: every result.ctrf.json must validate or build fails

### Stage 4 — CTRF data enrichment (Package B, ~3h)

- [ ] 4.1 Add prompt history capture in `orchestrator.py`:
      every user input → append to `_prompt_history` with timestamp
- [ ] 4.2 Emit `extra.evoQa.promptHistory[]` in CTRF root
- [ ] 4.3 Tag generated test scripts with metadata at write time:
      - `extra.scriptGeneratedAt` (ISO 8601 from time.time())
      - `extra.scriptGeneratedBy` ("evo-qa/1.1.0")
      - `extra.language` ("python" | "javascript")
      - `extra.lineCount`, `extra.sha256`
- [ ] 4.4 Embed scripts as `tests[].attachments[]` with `contentType: text/x-python` or `text/javascript`
- [ ] 4.5 Inject brain insight into `tests[].ai` field (use existing brain query)
- [ ] 4.6 Populate `tests[].steps[]` from ExplorerLoop phases
- [ ] 4.7 Populate `summary.flaky` from heal_pass count

### Stage 5 — HTML view layer (Package B, ~5h)

- [ ] 5.1 Write `core/reporting/html_render.py` — consume CTRF JSON, emit HTML
- [ ] 5.2 4-section canonical layout:
      - Section 1: Summary (4 stat cards)
      - Section 2: Charter & Prompt History
      - Section 3: Test Cases (collapsible, with steps + ai + script + screenshots)
      - Section 4: Insights & Brain Contributions
- [ ] 5.3 Self-contained: CTRF JSON inlined as `<script type="application/json">`
- [ ] 5.4 Apply brand styling:
      - 4px orange `#FD5108` top stripe
      - Helvetica Neue + system fallbacks
      - Pass green `#21812D`, fail red `#C52A1A`, flaky amber `#FFB600`
      - Datasheet table style
- [ ] 5.5 Vanilla JS: collapse/expand test cases, prettify dates, copy script source
- [ ] 5.6 No external CDN, no logo, favicon allowed
- [ ] 5.7 Snapshot test: render same CTRF → byte-identical HTML

### Stage 6 — Knowledge portability (Package D, ~3h)

- [ ] 6.1 Add `core/export/mem0_export.py` — convert brain → mem0 OSS-compatible JSON
- [ ] 6.2 Add `core/export/ctrf_bundle.py` — bundle multi-run CTRF into one tarball
- [ ] 6.3 Add `cli export --format mem0 --out path.json`
- [ ] 6.4 Add `cli export --format ctrf --out path.tar.gz`
- [ ] 6.5 Add `cli export --format json` (raw brain dump, our native format) for round-trip
- [ ] 6.6 Write `references/sharing-brain.md` — guide: how to share brain with others

### Stage 7 — BM25 retrieval (Package E, ~3h)

- [ ] 7.1 Vendor `rank_bm25` single-file (Apache 2.0) into `core/_vendor/rank_bm25.py`
- [ ] 7.2 Add `core/system_brain/bm25_index.py` — build index from brain entries
- [ ] 7.3 Hybrid score: substring (0.3) + bm25 (0.7) when entries > 200
- [ ] 7.4 Lazy index build (rebuild only when entries grow >10% since last build)
- [ ] 7.5 Cursor-on-disk: index serialized to `brain/.bm25.idx`
- [ ] 7.6 Test: 1000-entry synthetic brain, verify bm25 finds entries substring misses

### Stage 8 — Documentation (Package F, ~2.5h)

- [ ] 8.1 Rewrite `README.md` — user-facing, with mem0/CTRF standard links
- [ ] 8.2 Update `INSTALL.md` — new dir layout, post-install verification
- [ ] 8.3 Write `references/sharing-brain.md` (already in 6.6, expand here)
- [ ] 8.4 Update `CHANGELOG.md` v1.1.0 — full breakdown by package

### Stage 9 — Tests + audit + release (Package G, ~2.5h)

- [ ] 9.1 Run full 46+ test suite + new BM25 + new CTRF emit/validate tests
- [ ] 9.2 Run audit (12 existing items + new item 13: CTRF schema validation)
- [ ] 9.3 Manual smoke test: ingest sample → plan → run → report → validate-ctrf
- [ ] 9.4 Build tarball + zip
- [ ] 9.5 Write `v1.1.0-NOTES.md` (release notes for user)
- [ ] 9.6 Bump SKILL.md frontmatter version → `1.1.0`
- [ ] 9.7 Tag in git (if applicable)


---

## 🚦 Dependency graph (execution order)

```
Stage 0 (pre-flight)
    │
    ▼
Stage 1 (dir restructure) ────────► Stage 2 (SKILL.md update)
    │                                    │
    ▼                                    ▼
Stage 3 (CTRF data layer) ─────────► Stage 4 (CTRF enrichment)
    │                                    │
    └────────────────┬───────────────────┘
                     ▼
                Stage 5 (HTML view layer)
                     │
    ┌────────────────┼────────────────┐
    ▼                ▼                ▼
Stage 6           Stage 7         Stage 8
(export)          (BM25)          (docs)
    │                │                │
    └────────────────┼────────────────┘
                     ▼
              Stage 9 (test + release)
```

**Critical path**: 0 → 1 → 2 → 3 → 4 → 5 → 9 (≈ 22h)
**Parallel-able**: 6, 7, 8 can interleave after Stage 5

---

## ⚠️ Risk register

| Risk | Mitigation |
|---|---|
| Dir rename breaks imports | Stage 1.7 covers it; 46/46 must pass before next stage |
| SKILL.md edit hurts AI trigger | Stage 2 keeps original "20-year QA" voice; only adds directives |
| CTRF schema strictness rejects our extras | All extras go in `extra` (spec-allowed extension point); validated locally |
| BM25 vendor file breaks portability | rank_bm25 is single Python file, Apache 2.0, zero deps |
| Mem0 JSON format drift | Pin to mem0 OSS v3 schema (April 2026); document version in export header |
| HTML report bloats >100KB | Lazy-load screenshots as base64 only on click |
| Cline rc1 reveals critical bug late | Stage 0.2 reads feedback first; if blocking, fix before Stage 1 |

---

## 📐 Invariants (do not violate)

1. **Backward compat**: old `result.json` files in existing runs/ keep working (read-only support)
2. **No external runtime deps**: mem0 export produces a file, doesn't require mem0 lib
3. **No CDN in HTML**: everything inline (font fallback to system)
4. **Audit always green**: every PR run must pass all 13 audit items
5. **Tests grow, never shrink**: 46 → 60+ by end of v1.1.0
6. **CTRF compliance is hard contract**: report not "done" until `validate-ctrf` exits 0
7. **AI trigger keywords preserved**: SKILL.md description keywords (QA, Playwright, etc.) untouched
8. **No PII in exported brain**: `cli export` strips any user-identifying paths

---

## 📊 Success criteria for v1.1.0 release

- [ ] All 9 stages complete
- [ ] 60+ unit tests passing
- [ ] All 13 audit items green
- [ ] Manual smoke test on a real enterprise-like target succeeds end-to-end
- [ ] `validate-ctrf` returns 0 on every run output
- [ ] Generated HTML report renders correctly in Chrome + Safari + Firefox
- [ ] `cli export --format mem0` produces JSON that mem0 import accepts
- [ ] BM25 retrieval beats substring on synthetic 1000-entry test
- [ ] SKILL.md still <500 lines, <5000 tokens
- [ ] Skill dir name is `evo-qa` (hyphen, spec-compliant)
- [ ] No `evo_qa` slash-prefixed CLI strings in user-facing output
- [ ] Tarball + zip + NOTES.md delivered to `/app/working/exports/`

---

## 🎯 Definition of Done

> v1.1.0 ships when:
>
> 1. A user can `npx skills add` (or copaw install) the skill from a fresh client
> 2. They can run an end-to-end test on a sample web app
> 3. The generated report contains: charter + prompt history + test scripts (with timestamp) + AI insights — all in CTRF format
> 4. The HTML report looks branded and self-contained
> 5. They can `cli export --format mem0` and share the file with a colleague
> 6. The colleague can import it via stock mem0 tools
>
> **No "but"s. No "in v1.2 we'll fix that"s. Ship it clean or don't ship.**

---

## 📅 Schedule estimate

| Day | Stages | Hours | Deliverable |
|---|---|---|---|
| Day 1 | 0 + 1 + 2 | 5-6h | Restructure + SKILL.md done, 46/46 still pass |
| Day 2 | 3 + 4 | 8h | CTRF data layer + enrichment, validate-ctrf works |
| Day 3 | 5 | 5h | HTML report renders, snapshot test passes |
| Day 4 | 6 + 7 | 7h | Export + BM25 done |
| Day 5 | 8 + 9 | 5h | Docs + audit + tarball |
| Buffer | rc1 fixes + polish | 3-5h | |
| **Total** | | **~33-36h** | |

---

## 🛑 Stop conditions (when to halt and ask)

If any of these happen mid-implementation, stop and ask user:

- A stage ends up >2x its estimate
- 46+ test count drops (regression)
- A package conflicts with another in unexpected ways
- A user-facing decision point that wasn't in this plan
- rc1 reveals a fundamental design flaw

---

## ✍️ Sign-off

- **User**: approved scope + version v1.1.0 (2026-06-18)
- **Plan author**: agent (this document)
- **Start trigger**: user says "go" / "开始" / "开干"
- **First checkpoint**: end of Stage 1 (after dir restructure, before any code changes beyond paths)

