<p align="center">
  <img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/status-beta-yellow" alt="Status">
</p>

<h1 align="center">🧪 Evo QA</h1>
<p align="center"><strong>A self-evolving QA agent — learns your app, plans tests, runs Playwright, remembers across projects.</strong></p>

<p align="center">
  Not a test runner. An evolving QA engineer in a box.
</p>

<p align="center">
  🌐 <a href="README.md">English</a> | <a href="README.zh-CN.md">中文</a>
</p>

---

## Why Evo QA?

Most QA automation is **write once, maintain forever**. You write tests, the app changes, tests break, you fix them. Repeat forever.

Evo QA flips the model:

- **Feeds on your docs and screenshots** — give it a spec, it plans tests
- **Runs Playwright** — executes tests, captures evidence, diagnoses failures
- **Learns your app** — distills page objects, forms opinions about how things work
- **Remembers across projects** — carries experience so each new project starts smarter than the last

It's built for **SDETs, QA engineers, and agent-first teams** who want a QA companion that gets better over time.

---

## ✨ Features

| Capability | What it does |
|-----------|--------------|
| **🧠 Self-evolving** | Learns from every run — failures, patterns, app structure — and applies knowledge to future tests |
| **📋 Test planning** | Given a description or spec, produces structured test plans with edge cases |
| **🤖 Playwright execution** | Runs tests, takes screenshots, captures network logs, diagnoses failures with AI |
| **🗂️ Knowledge memory** | Remembers app structure, recurring issues, and test patterns across sessions and projects |
| **📊 CTRF reports** | Every run produces a standard `result.ctrf.json` — CI-friendly, tool-portable |
| **🧩 Agent skill** | Packaged as an [agentskills.io](https://agentskills.io) skill — works with any compatible host |
| **📤 Knowledge export** | Export accumulated knowledge as mem0 JSON, CTRF bundle, or raw brain dump |
| **🔌 Adapter architecture** | Plug in different browsers, executors, ingestors, and reporters |

---

## 🚀 Quick start

Evo QA is an **agent skill** designed to run inside a compatible agent host (e.g. CoPaw).

### Install the skill

1. [Download the latest ZIP](https://github.com/cheng372817884/evo-qa-skill/archive/refs/heads/main.zip)
2. Extract and import the folder into your AI client as a skill

### Use it

Once installed, ask your agent host something like:

> "Test the login flow of my app at https://example.com"

Evo QA will:
1. Analyze the page and plan tests
2. Execute them with Playwright
3. Capture screenshots and network logs
4. Produce a structured CTRF report

No test scripts to write. No CI pipelines to maintain. Just tell it what to test.

---

## 📸 What a run looks like

```
myapp/
├── runs/
│   └── 2026-06-20_153042/
│       ├── result.ctrf.json       ← standardized test report
│       ├── evidence/
│       │   ├── step-01-login.png
│       │   ├── step-02-dashboard.png
│       │   └── network-log.har
│       └── diagnosis.md           ← AI failure analysis
├── brain/
│   ├── system/                    ← mechanical facts about the app
│   └── business/                  ← learned business logic
└── plans/
    └── login-flow.md             ← generated test plan
```

---

## 📚 Documentation

| File | What it's for |
|------|---------------|
| [`SKILL.md`](SKILL.md) | Full operating manual — **start here** |
| [`INSTALL.md`](INSTALL.md) | Detailed setup & first run |
| [`CHANGELOG.md`](CHANGELOG.md) | What changed in each version |
| [`ATTRIBUTION.md`](ATTRIBUTION.md) | Open-source credits & how to attribute |
| [`references/VISION.md`](references/VISION.md) | Design philosophy & long-term roadmap |

---

## 🧪 Tested

- **68 / 68 passing** (Python 3.11, Linux)
- Python 3.10+
- Playwright with Chromium (default)
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
- **PRs**: Please open an issue first to discuss what you'd like to change
- **Style**: Follow the existing patterns — the project values clarity over cleverness

---

<p align="center">
  <sub>Built with 🧪 for QA engineers who believe testing should get easier, not harder.</sub>
</p>
