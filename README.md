<p align="center">
  <img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License">
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/status-beta-yellow" alt="Status">
</p>

<h1 align="center">🧪 Evo QA</h1>
<p align="center"><strong>A self-evolving QA agent — learns your app, plans tests, runs Playwright, remembers across projects.</strong></p>

<p align="center">
  Not a test runner. An evolving QA engineer in a box.
</p>

---

## What is Evo QA?

Evo QA is an **AI agent skill** — a reusable intelligence package for AI coding tools (Claude Code, Cursor, Copilot, and any agentskills.io-compatible host).

**You don't run commands. Your AI does.**

Think of it as a **junior QA engineer you're mentoring**. You describe what to test in natural language — just a sentence or two, no formal test case format needed. The AI takes it from there:

- **Proactively explores** every page of your app — buttons, forms, navigation, modals — building a mental model of how things work
- **Records real business scenarios and workflows** — not just isolated test cases, but the actual paths users take through your application
- **Generates reusable Playwright scripts** — after each run, it distills what it learned into ready-to-run Playwright test code you can check into your repo
- **Learns on the job** — every run, every bug, every new page adds to its understanding. The more you use it, the sharper it gets
- **Carries experience across projects** — what it learned from App A makes it better at testing App B from day one

It's like training an intern who never forgets, never needs a vacation, and gets exponentially more valuable the longer you work with it.

The only requirement is **Python 3.9+**. Your AI handles the rest — dependencies, Playwright browsers, everything.

---

## ✨ Features

| Capability | What it does |
|-----------|--------------|
| **🧠 Mentored learning** | Like a QA intern you're training — describe what to test in plain language, it figures out the rest and gets better with every project |
| **🔍 Proactive exploration** | Doesn't wait for instructions. It navigates your app, maps out pages, discovers workflows on its own |
| **📋 Natural language cases** | Describe a test in one sentence: "user logs in and checks the dashboard." No step-by-step format needed. |
| **🤖 Playwright execution** | Runs tests, captures screenshots, logs network traffic, diagnoses failures with AI |
| **🔄 Reusable script generation** | After each run, the AI distills what it tested into ready-to-run Playwright `.spec.ts` files you can commit and reuse |
| **🗂️ Business workflow memory** | Remembers real user journeys — not just selectors, but the business scenarios and end-to-end flows it discovered |
| **📊 CTRF reports** | Every run produces a standard `result.ctrf.json` + self-contained HTML report |
| **📤 Knowledge export** | Export accumulated experience as mem0 JSON or CTRF bundle — share with your team |

---

## 🚀 Quick start

### Prerequisites

- **Python 3.9+**
- An **AI coding tool** that supports agentskills.io skills

### Setup

**Step 1:** Clone the skill:

```bash
git clone https://github.com/<your-org>/evo-qa.git
```

**Step 2:** Tell your AI what to test.

That's it. **Two steps.** The AI reads the skill manual, checks your environment, installs anything missing, and gets to work.

> 💡 No need to know Playwright, browsers, or CTRF. Just describe what you want tested.

---

## 🎯 Demo: Testing TodoMVC

Here's what happens when you tell your AI: *"Test the TodoMVC app at https://demo.playwright.dev/todomvc"*

The AI probes the page, finds an input field, a todo list, and footer filters (All / Active / Completed). Then it plans and runs these scenarios — each described in **a single sentence of natural language, no step-by-step format**:

---

**TC-001 — Add a todo item**
Type something into the input box and press Enter. The todo should appear in the list below, and the counter should update to show how many items remain.

**TC-002 — Mark a todo as completed**
With a few todos already in the list, click the checkbox next to one. It should show as checked, the count should decrease, and a "Clear completed" button should appear.

**TC-003 — Filter by Active**
Click the "Active" filter. Only uncompleted todos should be visible. Completed ones should be hidden.

**TC-004 — Filter by Completed**
Click the "Completed" filter. Only completed todos should show up. The URL should reflect the current view.

**TC-005 — Clear completed todos**
With at least one completed todo, click "Clear completed". All completed items should be removed, leaving the list empty.

**TC-006 — Generate a test report**
Ask the AI to produce the report. A self-contained HTML file with all results, screenshots, and AI diagnosis should be generated — usable offline with no server or CDN.

---

### Result

| Case | Scenario | Status |
|------|----------|--------|
| TC-001 | Add a todo item | ✅ Passed |
| TC-002 | Mark a todo as completed | ✅ Passed |
| TC-003 | Filter by Active | ✅ Passed |
| TC-004 | Filter by Completed | ✅ Passed |
| TC-005 | Clear completed | ✅ Passed |
| TC-006 | Generate HTML report | ✅ Passed |

All evidence, screenshots, and reports are saved. The AI remembers what it learned for next time.

**And it doesn't stop there.** After execution, the AI distills everything into **reusable Playwright test scripts** — ready-to-run `.spec.ts` files you can check into your repo, run in CI, or share with your team. Your natural language descriptions become automated tests, no manual translation needed.

---

## ⚙️ Workflow

```
You say "test this app"  →  AI + Evo QA  →  Reports out
                                   │
                        ┌──────────┼──────────┐
                        ▼          ▼          ▼
                    ① Probe    ② Plan     ③ Execute
                        │          │          │
                        ▼          ▼          ▼
                  Snapshot DOM   Write      Run Playwright
                  no guessing    plan.md    capture evidence
                        │          │          │
                        └──────────┼──────────┘
                                   ▼
                         ┌─── ④ Report ────┐
                         │ CTRF JSON       │
                         │ + HTML report   │
                         └─────────────────┘
                                   │
                         ┌─── ⑤ Learn ─────┐
                         │ Store in brain/ │
                         │ Smarter next    │
                         │ time            │
                         └─────────────────┘
```

| Step | What happens |
|------|-------------|
| **① Probe** | AI snapshots the page — reads actual DOM, no blind selectors |
| **② Plan** | Produces a natural language test plan with scenarios |
| **③ Execute** | Runs each scenario via Playwright, captures screenshots + network logs |
| **④ Report** | Generates CTRF JSON + self-contained HTML report (offline, no CDN) |
| **⑤ Script** | Distills test scenarios into reusable Playwright `.spec.ts` files |
| **⑥ Learn** | Saves findings to `brain/`, so next project starts smarter |

---

## 🧠 Memory & Knowledge

```
     Project A                    Project B
 ┌──────────────────┐      ┌──────────────────┐
 │  brain/          │      │  brain/          │
 │  ├─ system/      │      │  ├─ system/      │
 │  ├─ business/    │      │  ├─ business/    │
 │  └─ insights.md  │      │  └─ insights.md  │
 └────────┬─────────┘      └────────┬─────────┘
          │                         │
          └────────┬────────────────┘
                   │
          ┌────────▼────────┐
          │  cli export     │
          │  → mem0 JSON    │
          └────────┬────────┘
                   │
          ┌────────▼────────┐
          │  New project /  │
          │  New agent      │
          │  inherits all   │
          │  experience     │
          └─────────────────┘

     Shared across all projects:
     📁 heuristics/  → SFDIPOT, RCRCRC testing patterns
     📁 glossary/    → industry terms
```

| Memory type | Scope | What's stored |
|-------------|-------|--------------|
| **Project knowledge** | Per project (`brain/`) | Page structure, selectors, flows, past issues |
| **Heuristics** | Shared across projects | Universal test patterns (boundary analysis, etc.) |
| **Glossary** | Shared | Domain-specific terminology |
| **Export** | Portable | `cli export --format mem0` — share with your team |

> 📖 Knowledge follows [Google OKF (Open Knowledge Format)](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) spec.
> Team members can export knowledge via `cli export` and import with `cli brain import`.
> Testing experience is no longer personal — the whole team benefits.

---

## 📚 Documentation

| File | What it's for |
|------|---------------|
| [`SKILL.md`](SKILL.md) | Operating manual for your AI — **the AI reads this, not you** |
| [`README.md`](README.md) | This file — human overview |
| [`INSTALL.md`](INSTALL.md) | Manual setup reference |
| [`CHANGELOG.md`](CHANGELOG.md) | Version history |
| [`ATTRIBUTION.md`](ATTRIBUTION.md) | Open-source credits & attribution guide |
| [`references/VISION.md`](references/VISION.md) | Design philosophy & roadmap |

---

## 🧪 Tested

- **68 / 68 passing** (Python 3.11, Linux)
- Python 3.9+
- Playwright with Chromium
- Agentskills.io v1 compatible
- CTRF v1.0 output

---

## 📄 License

**Apache 2.0** — free to use, modify, and distribute.  
Attribution required — see [`ATTRIBUTION.md`](ATTRIBUTION.md) for details.

---

## 🤝 Contributing

Evo QA is in early beta. Contributions, issues, and ideas are welcome.

- **Issues**: Bug reports, feature requests, questions
- **PRs**: Open an issue first to discuss what you'd like to change
- **Style**: Follow the existing patterns — clarity over cleverness

---

<p align="center">
  <sub>Built with 🧪 for QA engineers who believe testing should get easier, not harder.</sub>
</p>
