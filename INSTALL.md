# Install Guide — Evo QA v1.0.3

## Prerequisites

- **Python 3.11+** (3.10 may work; tested on 3.11)
- **pip** or **uv**
- Linux, macOS, **Windows 10/11**, or WSL2 — all first-class supported.

## 1. Place the skill

Put the `evo_qa` folder where your agent runtime expects skills.

For Claude Code / Copaw / Cline conventions:

```
<your-skills-dir>/
└── evo_qa/
    ├── SKILL.md
    ├── core/
    └── ...
```

The skill self-identifies via `SKILL.md` — your agent will pick it up automatically if it scans the skills directory.

## 2. Install Python dependencies

**Core install (all platforms):**

```bash
pip install playwright pyyaml jinja2 click
playwright install chromium
```

That's it. **No GTK, no Cairo, no Pango, no system libraries.** Reports are rendered as self-contained HTML files; if you need a PDF, just open the report in a browser and use Print → Save as PDF.

Optional (only if you want PDF/DOCX/XLSX/image **ingestion** — feeding these files into the agent as reference material):

```bash
pip install pypdf python-docx openpyxl pillow
```

**Strongly recommended** (for the credential store, so passwords go into the OS keyring instead of a base64 file):

```bash
pip install keyring
```

Without `keyring`, Evo QA still works — but the only place to save passwords is a base64-encoded file at `~/.evo_qa/credentials.yaml`, and you'll be prompted to consent every time. With `keyring`, your password lives in the OS-native secret store (macOS Keychain / Windows Credential Manager / Linux Secret Service).

## 3. Verify

From the parent of the `evo_qa/` folder:

```bash
python -m evo_qa.core.cli doctor
```

You should see all 11 checks pass. If anything is red, run:

```bash
python -m evo_qa.core.cli setup
```

## 4. First project

```bash
# Initialize a workspace.
python -m evo_qa.core.cli init saucedemo --url https://www.saucedemo.com

# (Optional) feed it material.
python -m evo_qa.core.cli ingest saucedemo path/to/spec.pdf

# Plan tests.
python -m evo_qa.core.cli plan saucedemo "test login with valid and invalid credentials"

# Run.
python -m evo_qa.core.cli run saucedemo

# (Optional) watch the browser.
python -m evo_qa.core.cli run saucedemo --headed

# Learn from the run.
python -m evo_qa.core.cli learn saucedemo

# Generate a self-contained HTML report.
python -m evo_qa.core.cli report saucedemo <run-id>

# Check overall health.
python -m evo_qa.core.cli health saucedemo
```

## 5. Workspace location

By default a workspace is created at:

```
./qa_workspace/<project-name>/
├── changes/           # planned change packages
├── runs/              # historical run records
├── tests/             # generated pytest specs
├── reports/           # rendered HTML reports
├── brain/             # auto-extracted facts + reverse-feedback bus
│   ├── system/
│   ├── business/      # LLM proposals (require human review)
│   ├── .bus/          # events.jsonl + cursors + dead-letter
│   └── .scheduler/    # job cursors
└── _meta/             # curator briefs, etc.
```

Override the workspace root via the `EVO_QA_WORKSPACE` environment variable.

---

## Platform notes

### Windows (PowerShell)

```powershell
# 1. Make sure Python 3.11+ is on PATH (winget works fine)
winget install Python.Python.3.11

# 2. Install dependencies
pip install playwright pyyaml jinja2 click
python -m playwright install chromium

# 3. Place the skill folder, then verify
python -m evo_qa.core.cli doctor
```

**Things to know on Windows:**

- **`python` vs `python3`** — Windows uses `python`. The commands above are written that way.
- **Long paths** — Windows 10 1607+ supports long paths but it's off by default. If you hit `[WinError 3]` errors, run as admin: `New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force` and reboot.
- **Avoid OneDrive / Dropbox sync folders** — atomic rename plus real-time sync can corrupt brain files. Put your workspace somewhere unsynced (e.g. `C:\qa-workspace` or `%LOCALAPPDATA%\qa-workspace`).
- **Chromium download blocked?** — `playwright install chromium` pulls ~150MB. If your firewall/proxy interferes, set `HTTPS_PROXY` first, or use the npm mirror: `set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright` (cmd) or `$env:PLAYWRIGHT_DOWNLOAD_HOST="https://npmmirror.com/mirrors/playwright"` (PowerShell).
- **Defender slowdown** — Windows Defender real-time scanning makes the brain layer noticeably slower. Add the workspace folder to its exclusion list if the cycle feels sluggish.

### macOS

```bash
brew install python@3.11
pip3.11 install playwright pyyaml jinja2 click
python3.11 -m playwright install chromium
python3.11 -m evo_qa.core.cli doctor
```

### Linux

```bash
sudo apt update && sudo apt install -y python3.11 python3-pip
pip3 install playwright pyyaml jinja2 click
python3 -m playwright install --with-deps chromium
python3 -m evo_qa.core.cli doctor
```

The `--with-deps` flag asks Playwright to install the C-library dependencies Chromium needs on Linux (libnss, libcups, etc.). On Windows and macOS, Chromium is self-contained — no system libraries needed.

### WSL2

Use the **Linux** instructions above. WSL2 is the recommended path if you're on Windows but want Linux-shaped behaviour.

---

## 6. Run the test suite (optional, for contributors)

```bash
# All architectural fault-injection tests
python evo_qa/scripts/test_decoupled.py

# Individual subsystems
python evo_qa/scripts/test_run_bus.py
python evo_qa/scripts/test_sinks.py
```

Expected: every script ends with "passed" / "OK".

## Troubleshooting

**`Playwright sync API cannot be used inside a Jupyter/asyncio event loop`**
You are inside an async runtime. Either run from a plain Python script, or use a subprocess wrapper.

**Watchdog complaints about threads**
The default mode is `soft`, which is correct for sync Playwright. The `threaded` mode is only for the async API.

**Reports look unstyled when opened locally**
The HTML report is fully self-contained: CSS is inlined, the favicon is an inline SVG data URI, and there are no external font/image/CDN dependencies. If you see unstyled output, the file was likely truncated during copy. Re-run `/qa:report <project> <run-id>`. The font stack is `"Helvetica Neue" → Helvetica → Arial → system sans-serif`, all locally available.

**I want a PDF**
Open the HTML report in any browser and Ctrl/Cmd + P → Save as PDF. Chromium's print-to-PDF gives the same rendering you see on screen.

**Workspace files corrupting on Windows**
Almost always caused by OneDrive/Dropbox/Google Drive syncing the workspace folder. Move the workspace out of the sync root.

## Upgrade notes from v1.0.2

- **WeasyPrint dependency removed.** Old `pip install weasyprint` is no longer needed; you can `pip uninstall weasyprint` if you previously installed it just for this skill.
- **Doctor now runs 11 checks instead of 12** (dropped weasyprint check).
- **`/qa:report` produces only HTML.** The `pdf_path` field in the report record is now always `null`. Generate PDFs from your browser if you need them.
- See `CHANGELOG.md` for the full v1.0.3 delta.
