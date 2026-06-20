# ATTRIBUTION — evo-qa

## 📜 Downstream Attribution (How to credit Evo QA)

Evo QA is released under the **Apache License 2.0**. If you use, modify, or redistribute this project, you must provide attribution as follows:

**In documentation or README:**
```
This project incorporates Evo QA (https://github.com/[your-org]/evo-qa),
licensed under Apache 2.0. See NOTICE and ATTRIBUTION.md for details.
```

**In source code:**
- Retain the copyright header in any Apache-licensed files you ship.
- If you modify Evo QA and distribute the modified version, include a prominent notice stating that you changed the files.
- If you distribute Evo QA as part of a larger work (binary, package, SaaS), include this attribution in the documentation, `About` dialog, or `NOTICE` file included with your distribution.

**Short form:**
> Keep the LICENSE, NOTICE, and ATTRIBUTION.md files. Give credit where it's due.

---

## 📚 Third-Party Attributions (What Evo QA borrowed from others)

This skill builds on prior open-source work. Each external project is listed here with what was borrowed, what was deliberately not borrowed, and license/repo information. The principle throughout is **"借形不抄魂"** (borrow form, not soul) — adopt methodologies and minimal interface contracts, write our own implementation, never copy code.

---

## P-series — Project-level inspirations (full subsystems borrowed)

### ★[P1] planning-with-files
- **Author**: Othman Adi
- **License**: MIT
- **Borrowed**: Three-file working memory pattern (`case_plan.md` / `findings.md` / `progress.md`), 5-question Reboot Test, 2-action rule, continue-after-completion mode → became Package B in v1.2
- **Not borrowed**: Claude Code hooks binding, SHA-256 attestation, autonomous/gated mode (host-tier dependent)
- **Where used**: REQUIREMENTS-v1.2.md Package B (B1-B5), `pq resume` CLI

### ★[P2] browser-act / skill-forge
- **Project**: BrowserAct
- **License**: MIT
- **Borrowed**: API-first decision tree, HAR offline verification, composite eval / info gain, failure → alternative means ladder, network capture adapter → became Package C in v1.2
- **Not borrowed**: Anti-bot (fingerprint / proxy), captcha solving cloud services, stealth mode matrix, confirmation gating
- **Where used**: REQUIREMENTS-v1.2.md Package C (C1-C5)

### ★[P3] browser-harness
- **Project**: Browser Use
- **License**: MIT
- **Borrowed**: URL-host brain surface, `brain/sites/<host>/*.md` markdown coexistence layer, SKILL.md "Decision priorities" 5-line tiebreaker → became §13 micro-enhancements in v1.2
- **Not borrowed**: Coordinate-click as execution mechanism (violates DOM-driven principle), `agent_helpers.py` Python extension (BA/QA can't program), CDP attach to user's real Chrome (breaks reproducibility), screenshot-only oracle, Browser Use Cloud / remote daemon
- **Where used**: REQUIREMENTS-v1.2.md §13.1-13.3

### ★[P4] self-improving-agent
- **Author**: Peter Skoett
- **License**: MIT
- **Borrowed (deferred to v1.3)**: `brain/learnings/` triage triplet (corrections / recurring-issues / feature-requests), pattern lifecycle status, promotion automation rules (recurrence ≥3 + cross ≥2 cases + 30-day window) → §14 v1.3 candidate seed
- **Not borrowed**: UserPromptSubmit hook (violates client-agnostic), `.learnings/` at project root (location conflict with our brain/), automatic skill extraction
- **Where used**: REQUIREMENTS-v1.2.md §14 (v1.3 candidate)

### ★[P5] OpenCLI
- **Author**: Jack Wener
- **License**: MIT
- **Borrowed**: `contract_level` decision methodology + empirical data (internal API maintenance frequency ~7-8× public API fix rate; UI selectors + semantic anchors are equivalent maintenance tier with cookie API → both `visible_ui`) → §15 §C1 patch in v1.2, refined further by §16 in v1.2
- **Not borrowed**: Chrome extension dependency, npm global install, daemon process / port 19825, 100+ public-site adapters (don't cover enterprise SUT), CLI-only interface (BA/QA can't use). All five would break our four core invariants.
- **Where used**: REQUIREMENTS-v1.2.md §15, §16

### ★[P6] OKF v0.1 (Open Knowledge Format)
- **Project**: GoogleCloudPlatform/knowledge-catalog
- **License**: Apache 2.0
- **Borrowed**: OKF SPEC.md (protocol body) + REDACTION RULES methodology from `agents/conversation_learner/SKILL.md` §3 → became v1.4 §20
- **Not borrowed**: Google ADK agents, Gemini integration, BigQuery enrichment, Knowledge Catalog Search (commercial product API), cytoscape visualizer (style mismatch, may revisit in v1.5)
- **Status caveat**: OKF v0.1 is Draft. v1.4 implementation declares `okf_version: "0.1"` per OKF §11. v0.2 will require fresh RFC.
- **Where used**: REQUIREMENTS-v1.4.md §20 (planned)
- **Repo**: https://github.com/GoogleCloudPlatform/knowledge-catalog
- **SPEC**: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md

---

## S-series — Standard / spec-level adoptions (open standards, full conformance)

### ★[S1] CTRF v1.0 (Common Test Report Format)
- **Type**: Open standard
- **Adopted**: v1.1.0
- **Borrowed**: Full JSON schema. evo-qa extensions go through `extra.evoQa.*` to preserve interop
- **Where used**: All `_runs/<run-id>/result.ctrf.json` outputs

### ★[S2] agentskills.io
- **Type**: Open standard
- **Adopted**: v1.1.0
- **Borrowed**: Skill packaging directory structure, manifest format
- **Where used**: This skill's directory structure (active_skills/evo-qa/)

### ★[S3] Mem0 OSS v3 (April 2026)
- **Type**: Open-source memory layer
- **Adopted**: v1.1.0
- **Borrowed**: Export schema only — `pq export --format mem0` produces compatible JSON. **No SDK dependency.**
- **Not borrowed**: Mem0 SDK runtime dependency (would violate self-containment), langchain dependency
- **Where used**: `pq export --format mem0` CLI

### ★[S4] rank_bm25
- **Type**: Library, single-file vendor
- **License**: Apache 2.0
- **Adopted**: v1.1.0
- **Borrowed**: Vendored as `src/_vendor/rank_bm25.py` for zero-transitive-dependency BM25 retrieval
- **Where used**: `brain/bm25_index/` build + retrieval

---

## Versioning of this file

This document grows with each new external borrow. Entries use append-only convention:
- New borrows get a new ★[X#] tag in P-series or S-series
- Modifications to existing borrows (e.g. expanded usage scope) get a dated note appended to the entry, not in-place edits
- Entries removed only if upstream relicenses incompatibly or we drop the borrow entirely (with reason logged)

Last updated: 2026-06-20 (P6 added per v1.4 RFC)
