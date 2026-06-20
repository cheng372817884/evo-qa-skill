# Changelog

All notable changes to Evo QA.

## [v1.1.1] — 2026-06-18 (hotfix)

> Six bug fixes discovered during real-world enterprise sandbox execution. All bugs were caught by virtue of being
> exercised on a real target — exactly the failure-discovery loop
> the skill was designed for.

### Fixed
- **B1** `playwright_adapter` — corporate sandboxes with self-signed certs need
  `ignore_https_errors=True` exposed as a runtime flag (was hardcoded false).
- **B2** `orchestrator` — referenced `decision.rationale` in two log paths;
  the dataclass field is `decision.reason`. Tests didn't catch it because
  fixture used a Mock that swallowed the AttributeError.
- **B3** `pytest_runner` — when generating ad-hoc test files outside the package
  layout, the runner now auto-writes a minimal `conftest.py` so fixtures
  resolve without manual setup.
- **B4** `loop._snapshot` — adapter outputs sometimes have top-level `text`/`role`
  fields rather than under `attrs`. Now uses defensive merge into `attrs`,
  preserving both shapes. (See lessons in `references/architecture-lesson-runbus.md`.)
- **B5** driver-script CLI — credential subcommand passed `backend=` but the
  underlying `CredentialStore` constructor takes `secret_backend=`. Renamed
  the CLI arg to match; added an alias for backward compat.
- **B6** `loop` LOGIN_SUCCESS / LOGIN_ERROR signals — heuristic now requires
  *two of three* signals (title-suffix change, login form detached, no
  alert role visible) instead of any one, eliminating false positives
  triggered by element names containing "Invalidate".

### Added — knowledge base
- New structural selector library for enterprise applications (top tabs, west-panel menus,
  form-input/button conventions). Pattern-only, no environment data.
- New `references/knowledge/heuristics/exploration/heuristic-probe-first.md`
  — methodology: dump DOM and decide, don't guess.
- New `references/knowledge/heuristics/exploration/heuristic-case-verb-parsing.md`
  — methodology: parse the case-title verb before writing selectors.
- New `references/knowledge/heuristics/exploration/heuristic-multi-match-warning.md`
  — methodology: a selector matching > 1 element is a smell, escalate.
- Extended enterprise quirks documentation with additional patterns
  (text-locator unreliability, conditional-required fields, etc.).

## [v1.2.0] — Planned (roadmap)

> **Design doc:** [`memory/evo_qa/REQUIREMENTS-v1.2.md`](../../memory/evo_qa/REQUIREMENTS-v1.2.md)
> (frozen design before any code — see "borrowed shape, kept soul" attribution there)

Driven by gaps observed in v1.1.1 real-world exercise **plus** two
external sources we studied carefully:
- [planning-with-files](https://github.com/OthmanAdi/planning-with-files) (Othman Adi, MIT) → Package B
- [browser-act/skills + skill-forge](https://github.com/browser-act/skills) (BrowserAct, MIT) → Package C

Each item links back to a specific friction event or a documented
external practice — never a hypothetical concern.

**Three packages, can ship as separate rcs:**
- **Package A** — Battle patches from enterprise exercise (`safe_click`, `data_precheck`, conditional-required, title watchdog, screenshot GC, principle automation)
- **Package B** — Persistent working memory (three-file markdown trio + `pq resume` + 2-action rule + continue mode)
- **Package C** — API-first exploration paradigm (decision tree, network adapter, HAR-offline safe verify, composite eval, failure→alternative-means ladder)


### Planned — selector-engine guardrails
- `safe_click` / `safe_fill` wrappers that pre-flight every selector with
  `count()`. Selectors with `count > 1` raise `AmbiguousSelector` and emit
  a WARNING event into the run's CTRF report.
  (Source: heuristic-multi-match-warning, enterprise quirk #8.)
- Auto-pivot: when ambiguity is detected and the target has a stable `id`
  or `name`, the engine automatically prefers it before falling back to
  scoped text.

### Planned — case-spec data preconditions
- New `data_precheck` block in case spec YAML — declares required seed
  data (e.g., "an Organization with name X must exist"). Runner verifies
  *before* the browser ever opens; absent data → fail-fast with a clean
  diagnosis, not a 5-step exploration loop. (Source: I-2 in retrospective.)

### Planned — probe-first as default behavior
- When MemoryGate has no entry for the current page, runner enters
  *probe mode*: dump visible inputs/buttons via `page.evaluate`, hand to
  LLM with the goal, execute the picked action, persist as a new
  brain pattern. Replaces blind guess-then-retry loops. (Source:
  heuristic-probe-first, ~30 retries saved on Create-Account.)

### Planned — conditional-required field detector
- After every "significant" interaction (popup close, page-state change,
  picker selection), runner re-snapshots required inputs. Fields that
  appeared post-interaction (like GW's `ProducerCode`) are filled in a
  second pass instead of being missed. (Source: enterprise quirk #9, F-3.)

### Planned — title-change watchdog as built-in signal
- For SPAs (detected by URL-stability heuristic), `wait_for_title_change`
  is a free per-step assertion. Currently per-case wiring; should be a
  default emit. (Source: I-6.)

### Planned — screenshot retention policy
- Auto-GC: keep last N=3 PASSED + last N=5 FAILED runs per case-id.
  Configurable. Current session left ~30MB of screenshots on disk.
  (Source: I-7.)

### Considered (not committed)
- `EnterpriseAdapter` plugin layer over `PlaywrightAdapter` — would
  package the navigation map and quirks as code. Held back because:
  (a) keeping selector knowledge in `references/knowledge/` is more
  portable, (b) plugin layer adds maintenance load before we know
  which patterns stabilize across multiple enterprise versions.

### Planned — persistent planning files (per case run)

> **Inspired by** [planning-with-files](https://github.com/OthmanAdi/planning-with-files)
> by Othman Adi (MIT). We adapt the methodology, not the code: their
> hooks bind to Claude Code, but Evo QA is client-agnostic, so
> the implementation is our own (driver-script invariants only).

For any case run, the skill maintains three markdown files alongside
the CTRF JSON and HTML report:

```
qa_workspace/<project>/_runs/<run-id>/
├── case_plan.md          ← phases, decisions, error table  ← NEW
├── findings.md           ← selectors, bugs, UI quirks       ← NEW
├── progress.md           ← chronological session log         ← NEW
├── result.ctrf.json      ← (existing) machine data layer
├── report.html           ← (existing) styled view layer
├── events.json           ← (existing) raw event stream
└── screenshots/
```

The CTRF/HTML pair remains the **reporting contract** (for CI,
dashboards, mem0 import). The three markdown files are the
**planning layer** — agent working memory persisted to disk.

**Implementation outline:**
- New `assets/case_templates/` with `case_plan.md`, `findings.md`,
  `progress.md` skeletons (heavily commented, like upstream).
- `runner` writes `case_plan.md` at run start by parsing the case
  spec into phases (verb + per-step entry points). Already aligns
  with v1.1.1's "case verb parsing" principle.
- `explorer_loop` calls `progress.append(step)` after every step
  and re-reads `case_plan.md` before each phase boundary.
- 2-action rule enforced by the loop: every 2 snapshots, the loop
  must write to `findings.md` before the next snapshot is allowed.
  (Lint, not hard-fail in v1.2.0; tighten later if useful.)

### Planned — cross-session resume (`pq resume <run-id>`)

> **Why this matters specifically for QA work:** enterprise cases
> routinely take 15-20 steps. A 200K-token context can fill within
> a single case. Without resume, a half-finished case is wasted.

- New CLI subcommand: `pq resume <run-id>`.
- Reads the three markdown files for that run.
- Prints the **5-Question Reboot Test** answers from disk:
  - Where am I? → `case_plan.md` `## Current Phase`
  - Where am I going? → remaining phases
  - What's the goal? → `case_plan.md` `## Goal`
  - What have I learned? → `findings.md` summary
  - What have I done? → `progress.md` session log tail
- Re-attaches credentials (already in keyring), restores browser
  state if a `state.json` exists in the run folder, lands on the
  in-progress phase.
- Stops if any of the three markdown files is missing or stale
  (mtime older than 30 days by default; configurable).

**Honest limitations** (call out in docs, do not pretend otherwise):

| Limit | Why |
|---|---|
| Browser cookies/CSRF tokens may have expired | Re-login is the recovery path, not magic resume. |
| The actual server-side state may have moved | Resume reads the *agent's* plan, not the *system's* state. The 5-Q test asks "where do *I think* I am", not "where does the server think we are". A `--reverify` flag re-probes the page before continuing. |
| Different LLM model on resume = different decisions | The plan files are the contract; the model still decides. No determinism promised. |

**Adapted from upstream's `session-catchup.py` concept**, but our
implementation reads our own markdown files, not Claude Code's
session DB. Client-agnostic.

### Planned — operating-principle automation

The four v1.1.1 operating principles plus the two added in v1.2's
roadmap (working memory on disk, two-action rule) are currently
*documentation that the agent must follow*. v1.2 promotes the most
mechanical of them into runtime checks:

- **Multi-match guardrail** → `safe_click` / `safe_fill` (already in v1.2 plan above).
- **Two-action rule** → loop counter, prompts agent to write before next probe.
- **Read-before-decide** → on phase boundary, runner re-reads `case_plan.md` and injects current phase + goal into the next prompt automatically.

The other principles (verb parsing, data precondition, probe-first)
stay as documentation; they are decision-level, not loop-level.

### Planned — API-first exploration paradigm (Package C)

> **Inspired by** [browser-act/skills + skill-forge](https://github.com/browser-act/skills)
> by BrowserAct (MIT). We adapt the methodology, not the matrix:
> their stealth/captcha/proxy concerns don't apply to first-party
> QA work, so we keep only the methodological core. Attribution
> in `references/knowledge/heuristics/exploration/`.

**Goal divergence is explicit and documented:**

| | browser-act / skill-forge | evo-qa v1.2 |
|---|---|---|
| Output | Reusable skill packages | QA reports + bug findings |
| API used for | Efficient data fetching | **Extra oracle**, validate UI vs backend |
| Side-effect tolerance | Commercial, acceptable | Must be zero-side-effect verification |
| Customer | RPA / data teams | Enterprise QA / BAs |

**API-first / DOM-fallback decision tree:**
- DOM oracle remains the default (current v1.1.1 behavior, unchanged).
- When `case spec` declares `oracles: [{kind: api, ...}]`, runner
  captures network traffic on the relevant step and validates
  response payload against the spec.
- API path is **opt-in**, never forced. No spec change → pure DOM.
- Failure on API path → fallback to DOM with a `path_fallback` event,
  not a hard failure. Reported transparently, never silent.

**`network capture` adapter:**
- New methods on `IBrowserAdapter`: `network_capture_start()`,
  `network_capture_stop(session_id)`, `network_requests(filter=)`,
  `offline(on: bool)`.
- Playwright impl uses native `page.on("request"/"response")` and
  `context.set_offline()` (no new dependency).
- HAR files persisted to `_runs/<id>/tmp/`, GC'd by retention policy.
- **Privacy invariant:** captured request bodies never enter CTRF;
  default-truncated in `findings.md`; agent must opt-in for full body.

**HAR + offline safe-verify protocol** (for destructive ops):
- For `verb: CREATE/SUBMIT/DELETE` cases that opt in, runner can
  validate the *outgoing* payload **without committing**:
  1. start capture → 2. go offline → 3. fill form + submit → 4. wait
  → 5. stop capture → 6. restore online → 7. nav to about:blank
- The captured POST is asserted to match expected method + URL +
  required body fields (per case spec).
- Strict opt-in via `verify_payload: {protocol: har_offline}`.
- Hidden from BA/QA UI by default — power-user feature.
- `try/finally` guarantees offline mode is always restored.

**Composite eval / information-gain rule** (methodology, not API):
- Promoted to operating principle 8.
- Encourages: batch selector probes in one `page.evaluate()`, prefer
  runtime state over DOM scraping, control output volume in-browser.
- Runner demonstrates this in its own selector verification path;
  agents pick up the pattern by example, not by mandate.

**Failure → alternative means ladder** (upgraded 3-strike):
- Promoted to operating principle 9.
- Failures are now classified at the adapter layer:
  - `deterministic` (clear error code / structure mismatch / 403) →
    abandon this means immediately, don't retry with variations.
  - `transient` (timeout, dropped connection) → retry once only.
  - `framework_internal` (`__vue_app__`, React fiber, ng) →
    abandon on first failure, switch approach.
  - `api_unreachable` → degrade to DOM, log but don't block.
- Key insight from skill-forge: *"Return to the goal itself.
  Enumerate alternative means. Pick the next."* — not "retry harder".

### Planned — browser-harness inspired micro-enhancements (3 items, ~30 min total)

> **Source**: [browser-use/browser-harness](https://github.com/browser-use/browser-harness) review, 2026-06-19.
> Skeleton unchanged (DOM-driven testing, case spec YAML, CTRF reports, runner-babysits-agent).
> Only kept items that align with our goals; coordinate-click style was rejected (see §13 of v1.2 design doc).

**1. URL-host brain surface** — On `goto_url(url)`, runner emits `BRAIN_HOST_HIT` event with up to 10 filenames from `brain/sites/<host>/`. Cheap layer above BM25 (which stays as-is for cross-site / fuzzy queries). ~30 LOC.

**2. `brain/sites/<host>/` markdown coexistence layer** — New folder convention (zero code in v1.2):
```
brain/sites/<host>/
├── quirks.md       ← UI peculiarities, human-readable
├── flows.md        ← typical business flows
└── selectors.md    ← verified selector library
```
Agent decides when to promote `_runs/<id>/findings.md` items to `brain/sites/`. JSON `patterns/` remain the machine contract; markdown is the human-readable archive. Not indexed by BM25.

**3. SKILL.md "Decision priorities" 5-line preamble** — Tiebreaker for the 9 operating principles when they conflict:
1. Truthfulness — never fake a pass.
2. Reproducibility — same case, same env → same outcome.
3. Helpful diagnosis — human language, not stack traces.
4. Low ceremony — solve the case, don't over-engineer.
5. Knowledge accumulation — feed the brain, leave durable findings.

### API oracle contract-level refinement (Package C, §C1 patch)

> **Source**: [opencli adapter-author skill](https://github.com/jackwener/opencli) review, 2026-06-19. OpenCLI itself rejected (extension dependency, public-site adapters not enterprise SUT, BA/QA-incompatible CLI), but their measured insight on API stability is gold.

OpenCLI's measured data: undocumented-internal API endpoints have **7-8× higher fix rate** than public-API endpoints. UI selectors with semantic anchors are at the same maintenance level as cookie-auth APIs (both `visible-ui` contracts).

Therefore Package C §C1 decision tree is patched:

- "API-first" is **not** absolute. The real axis is whether the data source has an external contract.
- `contract_level: stable | visible_ui | none` becomes a **required** field on `oracles[i]` of kind `api` in case spec.
- Runner behavior:
  - `none` + API failure → INFO event, not case failure
  - `stable` / `visible_ui` + API failure → case failure + WARN diagnosis
- DOM oracle is always **co-equal** to API oracle (case spec must have at least one DOM/visual oracle even if API is `stable`).
- `contract_level` lands in CTRF as `extra.evoQa.oracle.contractLevel`.

Full design in §15 of v1.2 design doc.

### Considered for v1.3 (not v1.2)

**Brain governance** — Inspired by [self-improving-agent](https://github.com/peterskoett/self-improving-agent) (Peter Skoett, MIT). Three pieces, must ship together:

1. `brain/learnings/` directory for cross-case knowledge that doesn't fit per-site quirks (corrections, recurring issues, feature requests).
2. Pattern lifecycle: `status` field on JSON patterns (`pending|stable|deprecated|promoted`) + `recurrence_count` + `last_seen`. BM25 weights stable patterns higher.
3. Promotion automation: `findings.md` → `brain/sites/<host>/` → `references/knowledge/heuristics/` driven by recurrence ≥ 3 + ≥ 2 distinct cases + 30-day window.

Held for v1.3 because: (a) v1.2 scope is already full, (b) brain governance is a coherent topic that needs to ship as one piece, (c) need v1.2 in production for a while before we have real data showing which patterns recur. Design seed is in §14 of v1.2 design doc.

### What v1.2 explicitly will NOT do

To prevent scope creep, the design doc enumerates non-goals:

- `pq forge <site>` (one-shot page-object package generation) — held for v1.3.
- Full `EnterpriseAdapter` plugin layer — case-spec extensions cover ~80%.
- Captcha solving, proxy, fingerprinting — violates portability.
- Multi-browser matrix (Firefox/WebKit) — Playwright already supports it.
- Mobile / native app — different philosophy entirely.
- MCP server / remote agent — permanent no per v1.0 §22.
- Replace brain with mem0 — already decided in v1.1.0 (path C: own brain + compatible export).
- Rewrite v1.0 / v1.1 design docs — history is append-only, forever.
- **Coordinate-click as execution mechanism** (browser-harness style `click_at_xy` in case specs / CTRF / brain) — violates our DOM-driven testing skeleton. Coordinates aren't human-readable in reports, break on layout changes, and the brain can't accumulate selector knowledge from them. If a future enterprise case proves selector-unsolvable, open a v1.3+ RFC that first solves: "how to express coordinate actions as selector-equivalent in CTRF" + "how brain learns from coordinate clicks". (Source: §13 of v1.2 design doc.)
- **`agent_helpers.py`-style agent-writes-Python extension** — BA/QA can't program is a hard constraint.
- **CDP attach to user's real Chrome** — QA needs reproducible environments.
- **Screenshot as sole oracle** — CTRF data oracle must remain. Screenshots supplement, not replace.
- **Browser Use Cloud / remote daemon integration** — violates client-agnostic + introduces external SaaS dep.

## [v1.2.0] — Planned (roadmap, push-back revisions 2026-06-19)

> Four push-back revisions to the v1.2 roadmap above, captured as REQUIREMENTS-v1.2.md §16-19. These take precedence over the v1.2.0 Planned sections above where they conflict.

### Revised — `contract_level` switched from required to overridable default (§16)

- `oracles[].contract_level` no longer required in case spec
- Default value: `visible_ui` (per OpenCLI [P5] data: stable & visible_ui have comparable maintenance cost)
- Power-users can override (`stable` / `none`) explicitly when they have engineering knowledge
- Runner auto-probes contract level on first hit per endpoint, writes hint to `brain/sites/<host>/contracts.md`
- **Why revised**: original "required" violated Priority 4 (Low ceremony) — BA/QA can't judge endpoint stability, 90% would noise-fill the field

### Added — Conflict test suite as freeze condition #5 (§17)

- `tests/principle_conflict/` with 5 v1.2-mandatory conflict scenarios (C1-C5)
- Each scenario runs N=10 against mock SUT, pass threshold 80%
- Principles failing the suite get re-worded (3 iterations) or **deleted from SKILL.md**
- Expected outcome: 14 rules (9 principles + 5 priorities) may shrink to 11-12. This is a feature, not regression.
- **Why added**: 14 rules without conflict testing are decorations, not constraints

### Revised — Brain promotion gate moved from v1.3 to v1.2 (§18)

- Original §13.4 "agent self-decides promotion" is positive-feedback contamination risk
- **v1.2 minimum gates** (mandatory, not deferred):
  - Gate 1: ≥2 independent runs observing same phenomenon
  - Gate 2: `<!-- promoted-from -->` origin marker required
  - Gate 3: Observation phrasing, not assertion phrasing
  - Gate 4: `pq_confidence` field required (single-run / multi-run / user-verified)
- BM25 index **extended to** `brain/sites/*.md` (§13.4 had said "not indexed" — corrected)
- New CLI: `pq brain promote` (validates 4 gates) + `pq brain doctor` (sanity audit, dry-run by default)
- **Why revised**: "open the gate first then build the fence" is engineering-unacceptable

### Added — Honest user persona + freeze condition #6 (§19)

- v1.x truthfully serves **semi-technical QA / SDET**, not "non-programming BA/QA"
- v1.0 §1 original wording preserved as **v2.0 north star**, not deleted
- v1.x docs synchronously down-shifted (`SKILL.md` persona section, README, CHANGELOG)
- New section in CHANGELOG: "v2.0 vision: zero-code QA" (separate roadmap)
- Freeze condition list grows from 4 → 6: items 5 (conflict test) and 6 (persona alignment) added
- **Why added**: marketing narrative (zero-terminal, non-programming) was inconsistent with actual entry points (pip, IDE, YAML, CLI). Three earlier push-backs all root-cause to this.

### Freeze conditions (revised, 6 items)

1. User ack of design doc ⬜
2. PLAN-v1.2.0.md complete ⬜
3. SKILL.md operating principles wording finalized ⬜
4. ATTRIBUTION.md complete ⬜
5. **(new §17)** Conflict test suite passing ⬜
6. **(new §19)** User persona aligned with actual entry points ⬜

---

## [v1.4.0] — Planned (RFC, OKF interchange)

> Knowledge sharing across users/orgs via Open Knowledge Format. RFC: REQUIREMENTS-v1.4.md §20.
> Depends on v1.3 brain governance shipping first.

### Planned — OKF v0.1 as evo-qa knowledge interchange format (§20)

- Adopt OKF SPEC (★[P6] GoogleCloudPlatform/knowledge-catalog, Apache 2.0)
- New CLI: `pq brain export --format okf` + `pq brain import okf-bundle`
- brain markdown gains `pq_*` extension frontmatter (preserved by OKF consumers per §4.1)
- Mandatory redaction pipeline (emails / tokens / capitalized identifiers / user rules)
- Import goes to `brain/_imported/` staging, not directly merged — review required
- Three-output strategy: CTRF (events) + Mem0 (agent memory) + OKF (human + portable knowledge)

### What v1.4 explicitly will NOT do

- Bundle Google ADK / Gemini / BigQuery / Knowledge Catalog product dependencies
- Adopt OKF visualizer (cytoscape HTML) — defer to v1.5 as optional viewer
- Auto-upload to any remote (P2P / cloud) — exports stay local, distribution is user's responsibility
- Honor external `pq_confidence: user-verified` — auto-downgraded to `multi-run` on import (their user-verified is not ours)
- Implement OKF on top of Knowledge Catalog SDK — markdown + pyyaml is enough

### Risks tracked

- OKF v0.1 is Draft — bundles declare `okf_version`, importer best-effort on unknown versions
- Cross-org data compliance (GDPR / CCPA / NDA) is user responsibility
- Redaction is heuristic, not deterministic — users must review exports before sharing

### Attribution

★[P6] OKF v0.1 — GoogleCloudPlatform/knowledge-catalog (Apache 2.0). Borrowed: SPEC + REDACTION methodology. Not borrowed: ADK agents, BigQuery enrichment, Knowledge Catalog Search. Repo: https://github.com/GoogleCloudPlatform/knowledge-catalog

---

## [v2.0.0] — Vision (zero-code QA, no commitment)

> Long-horizon north star, 12-18 months after v1.x stabilizes. Not on the implementation track yet.

- Real entry points for non-programming BA/QA: VSCode plugin / Web UI / Excel-driven case builder / browser-extension selector picker
- v1.x case spec / runner / brain / CTRF / OKF stays as **backend** — not rewritten
- v2.0 is **entry rewrite**, not design rewrite

---

## [v1.1.0] — 2026-06-18

> Major release: opens up to three industry standards.
>
> Scope (4 packages combined): rc1 feedback fixes + CTRF report
> standardization + agentskills.io compliance + knowledge portability.

### Added — CTRF v1.0 report standardization
- Every test run emits `result.ctrf.json` (CTRF v1.0 schema)
- `cli validate-ctrf <run-id>` for local validation
- HTML report becomes a view layer over CTRF JSON (styled, self-contained)
- Reports MUST contain: prompt history + test scripts (with timestamp) + AI insights
- New SKILL.md section: "Reports — STRICT REQUIREMENTS (DO NOT DEVIATE)"

### Changed — agentskills.io compliance (BREAKING for installers)
- Skill directory rename: `evo_qa/` → `evo-qa/` (lowercase + hyphen, spec-required)
- Python module name kept as `evo_qa` (Python disallows hyphens)
- Directory restructure: `knowledge/` → `references/knowledge/`,
  `templates/` → `assets/templates/`, `workspace_init/` → `assets/workspace_init/`,
  `prompts/` → `references/prompts/`
- `metadata.copaw.*` flattened to `metadata.copaw-emoji` etc. (spec: string→string)
- SKILL.md adds "When to load which file" directives

### Added — Knowledge portability (mem0 export)
- `cli export --format mem0` produces stock-`mem0 import`-compatible JSON
- `cli export --format ctrf` bundles multi-run CTRF
- `cli export --format json` raw brain dump
- New `references/sharing-brain.md` guide

### Added — BM25 retrieval index
- Vendor `rank_bm25` single-file (Apache 2.0) into `core/_vendor/`
- Hybrid scoring: substring + bm25 when entries > 200
- Solves the substring-quality-collapse beyond 5000 entries

### Added — Black-box scripts principle
- All bundled scripts must be invoked with `--help` first
- "DO NOT read source unless customization is absolutely necessary"

### Tests
- 74 invariants total (was 46 in v1.0.4-rc1)
- New: `test_ctrf.py` (11), `test_export.py` (4),
  `test_retrieval.py` (7) = 28 new tests
- All previous 46 still pass after the directory restructure

### Migration notes (for v1.0.x users)
- Skill directory is now `evo-qa/` (hyphen). Update your
  agent host's skill index accordingly.
- Python module imports are unchanged (`from evo_qa.core...`).
- Existing `<workspace>/` data is fully compatible — no migration
  needed. The first run after upgrading will start emitting
  `result.ctrf.json` next to existing run records.
- Reports rendered before v1.1 still load (legacy mode); they just
  don't show the four new sections (Prompt History / Scripts / AI
  Diagnoses / CTRF Data Layer). To upgrade: re-run `cli report`.

---

## [v1.0.4] — Unreleased

### Changed — Client-agnostic CLI hints

- All user-facing strings (error messages, `next` hints, README seeds,
  doctor output, workspace `insights.md` placeholder) now reference the
  **real CLI invocation** (`python -m evo_qa.core.cli <subcommand>`)
  instead of slash-command sugar (`/qa:init`, `/qa:plan`, …).
- Why: slash commands are a Copaw / Claude Code client-side UX. On
  Cline / Cursor / Aider / bare API, the AI tries to execute slash
  hints **literally as shell commands**, fails, retries, and burns
  through the budget. One real-world report: 1 hour spent on a 5-minute
  case because of this loop. Fixing the hints removes the loop without
  changing any actual command behavior.
- New `CLI` module-level constant in `core/orchestrator.py` —
  `"python -m evo_qa.core.cli"`. All hints reference this so
  there's a single source of truth.
- Error messages now also include a `next` field with the literal
  command to run, e.g.:
  ```json
  {"ok": false,
   "msg": "Workspace not initialized.",
   "next": "python -m evo_qa.core.cli init <project> --url <url>"}
  ```
- The slash form remains a Copaw / Claude Code shortcut: those clients
  translate `/qa:init` → CLI invocation. Other clients now see the
  CLI form directly. **Copaw users lose nothing.**

### Added — ExplorerLoop & MemoryGate

- New module `core/exploration/` — sniff-before-you-write capability.
  - `MemoryGate` decides whether exploration is needed at all, based on
    existing brain coverage (selectors / pages / recent reports).
    `score = w_sel*sel + w_page*page + w_recent*recent`. ≥0.8 → skip,
    ≥0.4 → partial, else full.
  - `ExplorerLoop` orchestrates one charter end-to-end: opens the
    browser, calls Strategy for next Action, runs Guards, executes,
    snapshots, persists discoveries.
  - Three Guards (silent-skip, no prompts):
    `BlacklistGuard` (destructive keywords), `OriginGuard`
    (cross-origin nav), `AlreadyDoneGuard` (loop prevention).
  - `LoginStrategy` MVP: 7-phase state machine (navigate → wrong fill×2
    → wrong click → real fill×2 → real click → stop) capturing both
    error and success paths.
  - `GenericStrategy` fallback for unclassified charters.
- `cmd_plan` now consults MemoryGate before opening a browser. Returns
  `memory_gate: { skip_exploration, scope, coverage_score, rationale,
  gaps }` so users can see *why* exploration was or wasn't run.
- 12 new invariants locked down by `scripts/test_exploration.py`
  (gate empty/medium/rich, login phases, happy path, wrong-creds path,
  guard behavior, read-only mode, no-form, report rendering).

### Added — Self-contained design reference

- New file `references/design-tokens.md` (~8 KB): the minimum
  subset reports actually need — favicon, color tokens,
  typography scale, spacing, required components, "what NOT to do".
- `SKILL.md` now explicitly tells the AI: **read this file before
  generating any new report HTML, and do not rely on a companion
  design skill being installed**. Bundles cannot assume their
  user's machine has companion skills.
- `INSTALL.md` clarified: reports are fully self-contained, no CDN
  loads. Earlier text suggesting CDN linking was inaccurate
  and removed.

## [v1.0.3] — 2026-06-18

### Added — Credential Store

- New module `core/credentials/` — user-level (cross-project) credential store.
- New CLI subcommand group: `creds list / add / remove / suggest`.
- Default storage: **OS keyring** (macOS Keychain / Windows Credential Manager / Linux Secret Service via the optional `keyring` package).
- Plaintext fallback (~/.evo_qa/credentials.yaml, base64-encoded, `chmod 600`) is **off by default**; enabling it requires explicit user consent in interactive mode or `--yes-plaintext` in non-interactive mode.
- Recency-weighted scoring: `score = uses * 0.5^(days_since_last_used / 30)`. The `creds suggest` command ranks by this.
- First-run wizard asks the user before saving anything; the default answer to "save?" is always **no**.
- Per-URL multi-account support: `(url, username)` is the key, not `url`.
- Index path: `~/.evo_qa/credentials.yaml` (POSIX), `%APPDATA%\evo_qa\credentials.yaml` (Windows). Override via `EVO_QA_HOME`.
- 10 invariants locked down by `scripts/test_credentials.py` (consent gating, no-leak, base64-only-on-disk, score decay, POSIX perms, etc.).

**What this does NOT do (deliberately):**
- No master password / no PBKDF2 / no Fernet — encryption is delegated to the OS keyring. Plaintext fallback is for convenience, not for secrecy.
- Passwords NEVER touch brain entries, run records, reports, plan documents, generated pytest code, or logs. Generated tests reference credentials via `${creds.<id>.password}` placeholders, resolved at run time.

### Removed — Windows-friendliness

- **WeasyPrint dependency dropped.** Reports are now HTML-only. WeasyPrint pulled in GTK3 / Cairo / Pango on Windows (~80MB of system libraries plus a non-trivial install path), which was the single biggest barrier for non-developer users on Windows. HTML reports render identically across all browsers, and any browser can produce a PDF via Ctrl/Cmd + P → Save as PDF.
- `adapters/reporters/html/render_pdf()` removed.
- `render_report(..., also_pdf=True)` is now a no-op kept for backward compatibility; `pdf_path` in the report record is always `null`.

### Changed — Cross-platform fixes

- `core/cli.py doctor` — disk-space check now uses `WORKSPACE_ROOT.resolve().anchor` instead of hard-coded `/`, so it works on Windows drive letters (`C:\`, `D:\`, …).
- Doctor check count: **12 → 11** (dropped `weasyprint` check).
- `INSTALL.md` rewritten with Windows as a first-class target: PowerShell snippets, OneDrive/Defender warnings, Long Paths note, Chromium download mirror.

### Testsed (no change required)

POSIX assumptions reviewed against Windows behaviour:

- `os.replace` — atomic on Windows NTFS ✅
- `os.fsync` — supported on Windows file handles ✅
- `O_APPEND` semantics — Windows respects it for sub-PIPE_BUF writes ✅ (`PIPE_BUF_SAFE=4000` left at Linux value; safe for single-process use, which is the default)
- `pathlib.Path` — fully cross-platform ✅
- No `signal.SIGALRM`, no `os.fork`, no `/tmp` hard-coding ✅

## [v1.0.2] — 2026-06-18

### Added — RunBus Decoupling

- `core/_atomic.py` — `atomic_write` (write+fsync+os.replace, per-process unique tmp) + `append_event` (O_APPEND, < 4KB) + `safe_read`
- `core/events.py` — `RunCompleted` / `RunFailed` event types with hard 4000-byte size guard
- `core/run_bus.py` — `RunBus` (publish never raises; tail; per-sink cursors; dead-letter; safe rotation)
- `core/sinks/` — `Sink` ABC + `SinkRetryable` + `ExtractorSink` (delegates to `BrainWriter`) + sink runner (per-sink isolation)
- `core/scheduler/` — `Job` ABC + `JobCursor` + zero-copy `Snapshot` (`view_at(snap)` lazy filter) + `CuratorJob` + `ReflectionJob` (LLM stub, count-triggered)
- `core/system_brain/writer.py` — `BrainWriter` mediator with field-ownership matrix
- 3 new commands: `curate`, `reflect`, `drain` (CLI total: 18)
- `scripts/test_decoupled.py` — 12 fault-injection tests for the SLA

### Changed

- `cmd_run_v1` — replaces inline brain ingest with `bus.publish(RunCompleted)` + `spawn_inline()` sidecar; main flow returns immediately on test completion
- `cmd_health` — now exposes RunBus stats, scheduler job state, dead-letter contents, and snapshot history
- `core/system_brain/storage.py` — `save()` goes through `atomic_write`; `_inflate` renamed `inflate` (public)

### Fixed

- Concurrent `atomic_write` from multiple processes: tmp filenames now include `pid` + random suffix to avoid `os.replace` race when two processes target the same final file
- `SystemBrain(brain_dir)` now consistently uses the `brain_dir/system/` subdirectory

## [v1.0.1] — 2026-06-17

### Added — Smart Dropdown

- 5-tier dropdown fallback (native select / Combobox role / typeahead / virtualized scroll / role+text)
- 13 atoms (12 + new `dropdown_select`)
- Validated against 4 carrier-template variants

## [v1.0.0] — 2026-06-17

### Initial Release

- Phase 1 — Doctor (12/12 environment checks)
- Phase 2 — Knowledge layer (~48 entries, retriever)
- Phase 3 — Atoms + Retry + Watchdog (12 atoms, e2e green)
- Phase 4 — Curator + Forgetting (honeymoon grace, never_archive, revive)
- Phase 5 — HTML+PDF report + full E2E (PDF removed in v1.0.3 — see above)
- 15 commands
- Validated end-to-end on real-world enterprise targets
