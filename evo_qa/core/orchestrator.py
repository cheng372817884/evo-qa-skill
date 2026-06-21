"""
L5 Orchestrator — high-level command orchestration.

Each `cmd_*` method corresponds to one CLI subcommand of
`python -m evo_qa.core.cli <subcommand>`. The orchestrator does
not depend on concrete adapters; it pulls them via the registry.

Note on user-facing strings: hints, next-step suggestions, and error
messages must reference the **real CLI invocation** (e.g.
`python -m evo_qa.core.cli init ...`), not slash-command sugar
(`/qa:init`). The slash form is a Copaw / Claude Code client-side
shortcut; on Cline / Cursor / bare API the AI will try to execute the
hint literally and fail. See `CLI` constant below.
"""

from __future__ import annotations
import json
import shutil
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

# Canonical CLI invocation prefix used in all user-facing hints and
# error messages. Any AI client (Copaw / Claude Code / Cline / Cursor /
# Aider / bare API) can execute this string verbatim in a shell.
CLI = "python -m evo_qa.core.cli"
from typing import Optional

import yaml

from . import registry
from .interfaces import Source
from .schemas import (
    Change, DeltaSpec, Knowledge, Requirement, Run, Scenario, Spec,
    Task, WorkspaceConfig, to_dict,
)
from .workspace import Workspace


# Built-in knowledge bundled with this skill.
#
# Layout (v1.1, agentskills.io compliant):
#     evo-qa/                  ← skill root (PKG_ROOT.parent)
#     ├── evo_qa/              ← Python package root (PKG_ROOT)
#     │   ├── core/orchestrator.py   ← __file__
#     │   └── ...
#     ├── references/knowledge/      ← BUILTIN_KNOWLEDGE
#     ├── assets/templates/
#     └── ...
PKG_ROOT = Path(__file__).resolve().parent.parent          # evo_qa/
SKILL_ROOT = PKG_ROOT.parent                                # evo-qa/
BUILTIN_KNOWLEDGE = SKILL_ROOT / "references" / "knowledge"


class Orchestrator:
    """High-level orchestration for every command."""

    def __init__(self, ws: Workspace):
        self.ws = ws

    # =====================
    # init
    # =====================
    def cmd_init(self, url: str, *, industry: str = "", language: str = "auto") -> dict:
        if self.ws.exists():
            return {"ok": False, "msg": f"Workspace already exists: {self.ws.root}"}
        cfg = WorkspaceConfig(
            name=self.ws.project, url=url, industry=industry, language=language,
        )
        self.ws.init(cfg)
        return {
            "ok": True,
            "msg": f"Workspace initialized at {self.ws.root}",
            "next": [
                f"{CLI} ingest <project> <file-or-url>   # feed me docs about this app",
                f"{CLI} plan <project> \"<test idea>\"   # let me design tests",
                f"{CLI} status <project>                  # check current state",
            ],
        }

    # =====================
    # ingest
    # =====================
    def cmd_ingest(self, location: str, *, kind: Optional[str] = None) -> dict:
        if not self.ws.exists():
            return {"ok": False, "msg": "Workspace not initialized.", "next": f"{CLI} init <project> --url <url>"}

        # Auto-detect source kind
        if kind is None:
            if location.startswith(("http://", "https://")):
                kind = "url"
            elif Path(location).exists():
                kind = "directory" if Path(location).is_dir() else "file"
            else:
                kind = "text"

        sources: list[Source] = []
        if kind == "directory":
            for p in Path(location).rglob("*"):
                if p.is_file():
                    sources.append(Source("file", str(p)))
        else:
            sources.append(Source(kind, location))

        ingested: list[Knowledge] = []
        skipped: list[str] = []
        for src in sources:
            ing = registry.pick_ingestor(src)
            if ing is None:
                skipped.append(f"{src.kind}: {src.location[:60]}")
                continue
            try:
                ks = ing.ingest(src)
                for k in ks:
                    self._save_project_knowledge(k)
                ingested.extend(ks)
            except Exception as e:
                skipped.append(f"{src.location[:60]} ({e})")

        return {
            "ok": True,
            "ingested": len(ingested),
            "skipped": len(skipped),
            "items": [{"id": k.id, "title": k.title, "type": k.type} for k in ingested],
            "skipped_items": skipped,
        }

    def _save_project_knowledge(self, k: Knowledge) -> None:
        """Write a knowledge entry into the project brain."""
        target_dir = self.ws.digest_dir if k.type in ("reference", "concept") else self.ws.specs_dir / "_global"
        target_dir.mkdir(parents=True, exist_ok=True)
        out = target_dir / f"{k.id}.md"
        # frontmatter + body
        fm = {
            "id": k.id, "type": k.type, "scope": k.scope,
            "title": k.title, "summary": k.summary,
            "tags": k.tags, "domains": k.domains, "priority": k.priority,
            "source_type": k.source.type, "source_ref": k.source.ref,
            "confidence": k.confidence, "review_state": k.review_state,
            "created_at": k.created_at, "updated_at": k.updated_at,
        }
        text = "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n\n" + k.body
        out.write_text(text)

    # =====================
    # plan
    # =====================
    def cmd_plan(self, intent: str, *, change_id: Optional[str] = None,
                 explore: bool = True) -> dict:
        if not self.ws.exists():
            return {"ok": False, "msg": "Workspace not initialized.", "next": f"{CLI} init <project> --url <url>"}

        cfg = self.ws.read_config()

        # 1. Retrieve relevant knowledge (builtin + project-local)
        retr = registry.get_retriever()
        retr.index([BUILTIN_KNOWLEDGE, self.ws.brain_dir, self.ws.specs_dir])
        relevant = retr.search(intent, top_k=8)

        # 2. Live exploration (optional; default on)
        #
        # MemoryGate (v1.0.4): before we open a browser, check whether
        # we already know enough about this intent. If so, skip the
        # snapshot — saves ~5-10s on warm projects and prevents brain
        # from accumulating duplicate observations.
        snapshot_data = None
        gate_decision = None
        if explore and cfg.url:
            try:
                from .exploration import MemoryGate, Charter
                kind = self._classify_charter_kind(intent)
                gate = MemoryGate(self.ws)
                gate_decision = gate.assess(Charter(
                    raw=intent, kind=kind, target_url=cfg.url,
                    project=getattr(cfg, "name", "default"),
                ))
            except Exception:
                # MemoryGate failures must never block planning.
                gate_decision = None

        if (explore and cfg.url
                and (gate_decision is None or not gate_decision.skip)):
            br = registry.get_browser()
            try:
                br.start(headed=False)
                br.goto(cfg.url)
                br.wait_for_load()
                snap = br.snapshot()
                snapshot_data = {
                    "url": snap.url,
                    "title": snap.title,
                    "elements": snap.elements,
                    "tree": snap.accessibility_tree,
                }
                # Persist discovered pages/elements to pages.md / selectors.json
                self._update_pages_map(snap)
                self._update_selectors(snap)
            finally:
                br.stop()

        # 3. Generate the change package
        # Map a free-form intent to an ASCII slug; fall back to a hash.
        ascii_slug = "".join(c if c.isascii() and (c.isalnum() or c == "-") else "-"
                             for c in intent.lower()).strip("-")[:40]
        if not ascii_slug or ascii_slug.replace("-", "") == "":
            # No ASCII letters present — use keyword heuristics
            intent_l = intent.lower()
            if any(k in intent_l for k in ["login", "signin", "sign-in"]):
                ascii_slug = "login"
            elif any(k in intent_l for k in ["checkout", "order", "purchase"]):
                ascii_slug = "checkout"
            elif any(k in intent_l for k in ["search", "query"]):
                ascii_slug = "search"
            elif any(k in intent_l for k in ["signup", "register"]):
                ascii_slug = "signup"
            else:
                ascii_slug = f"flow-{abs(hash(intent)) % 10000}"
        cid = change_id or f"test-{ascii_slug}"
        change_dir = self.ws.get_change_dir(cid)
        change_dir.mkdir(parents=True, exist_ok=True)

        # 4. Generate tasks using heuristics + snapshot
        tasks = self._derive_tasks(intent, snapshot_data, relevant)

        change = Change(
            id=cid,
            title=f"Test: {intent}",
            proposal=self._render_proposal(intent, relevant, snapshot_data),
            design=self._render_design(intent, snapshot_data, tasks),
            tasks=tasks,
            status="ready",
            created_at=datetime.utcnow().isoformat(),
        )

        self._write_change(change)

        result = {
            "ok": True,
            "change_id": cid,
            "change_dir": str(change_dir),
            "tasks": [{"id": t.id, "text": t.text} for t in tasks],
            "knowledge_used": [k.id for k in relevant],
            "next": [f"{CLI} run {self.ws.project} {cid}"],
        }
        if gate_decision is not None:
            result["memory_gate"] = {
                "skip_exploration": gate_decision.skip,
                "scope": gate_decision.scope,
                "coverage_score": round(gate_decision.coverage.score, 3),
                "rationale": gate_decision.reason,
                "gaps": gate_decision.coverage.gaps,
            }
        return result

    def _update_pages_map(self, snap) -> None:
        """Append discovered pages to pages.md."""
        page_id = snap.url.rstrip("/").split("/")[-1] or "home"
        line = f"\n## {page_id}\n- **URL**: {snap.url}\n- **Title**: {snap.title}\n- **Elements**: {len(snap.elements)}\n"
        existing = self.ws.pages_path.read_text()
        if f"## {page_id}\n" not in existing:
            self.ws.pages_path.write_text(existing + line)

    def _update_selectors(self, snap) -> None:
        """Update selectors.json — maintain selector scores."""
        try:
            data = json.loads(self.ws.selectors_path.read_text())
        except Exception:
            data = {"selectors": {}}
        sels = data.get("selectors", {})
        for el in snap.elements:
            key = f"{el['role']}:{el['name'][:30]}"
            if key not in sels:
                sels[key] = {
                    "selector": el["selector"],
                    "url": snap.url,
                    "score": 1.0,
                    "first_seen": datetime.utcnow().isoformat(),
                }
        data["selectors"] = sels
        self.ws.selectors_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    @staticmethod
    def _classify_charter_kind(intent: str) -> str:
        """Crude string classifier; v1.0.5 will use embeddings."""
        s = (intent or "").lower()
        for kw, kind in (
            ("login", "login"), ("signin", "login"), ("sign-in", "login"),
            ("登录", "login"), ("登入", "login"),
            ("checkout", "checkout"), ("payment", "checkout"),
            ("search", "search"), ("query", "search"),
            ("cart", "cart"), ("add to cart", "cart"),
            ("signup", "signup"), ("register", "signup"),
        ):
            if kw in s:
                return kind
        return "generic"

    def _derive_tasks(self, intent: str, snapshot_data, relevant) -> list[Task]:
        """Derive test tasks from the user intent, page snapshot, and retrieved knowledge.

        Default implementation: heuristic rules. An LLM-driven implementation can be plugged in via the same interface.
        """
        tasks: list[Task] = []
        intent_lower = intent.lower()

        # Detect intent kind
        is_login = any(k in intent_lower for k in ["login", "sign in", "auth", "signin"])
        is_form = any(k in intent_lower for k in ["form", "submit", "checkout", "purchase", "order"])

        if is_login and snapshot_data:
            # Locate username/password/submit elements
            els = snapshot_data["elements"]
            user_el = next((e for e in els if any(t in (e["name"] + e["selector"]).lower()
                            for t in ["user", "email"]) and e.get("type") != "password"), None)
            # Fallback: first non-password input field
            if user_el is None:
                user_el = next((e for e in els if e["role"] == "input"
                                and e.get("type") not in ("password", "submit", "button")), None)
            pass_el = next((e for e in els if "password" in (e["name"] + e["selector"]).lower()
                            or e.get("type") == "password"), None)
            submit_el = next((e for e in els if (
                                e["role"] in ("button", "submit")
                                or e.get("type") in ("submit", "button")
                             ) and any(t in (e["name"] + e["selector"]).lower()
                                       for t in ["login", "sign", "submit", "go"])), None)

            if user_el and pass_el and submit_el:
                url_r = repr(snapshot_data["url"])
                user_s = repr(user_el["selector"])
                pass_s = repr(pass_el["selector"])
                sub_s = repr(submit_el["selector"])

                code = [
                    f'page.goto({url_r})',
                    f'page.fill({user_s}, "standard_user")',
                    f'page.fill({pass_s}, "secret_sauce")',
                    f'page.click({sub_s})',
                    f'page.wait_for_load_state("networkidle", timeout=5000)',
                    f'assert "inventory" in page.url, f"Expected redirect to inventory, got {{page.url}}"',
                ]

                t1 = Task(id="1.1", text="Happy path: valid credentials redirect away from login")
                t1.steps = code  # type: ignore[attr-defined]
                tasks.append(t1)

                # Edge case 1: empty password
                code2 = [
                    f'page.goto({url_r})',
                    f'page.fill({user_s}, "standard_user")',
                    f'page.click({sub_s})',
                    f'# Should NOT redirect; expect error or stay on page',
                    f'assert "inventory" not in page.url, "Should not log in with empty password"',
                ]
                t2 = Task(id="1.2", text="Negative: empty password should not log in")
                t2.steps = code2  # type: ignore[attr-defined]
                tasks.append(t2)

                # Edge case 2: wrong password
                code3 = [
                    f'page.goto({url_r})',
                    f'page.fill({user_s}, "standard_user")',
                    f'page.fill({pass_s}, "WRONG_PASSWORD_xyz")',
                    f'page.click({sub_s})',
                    f'assert "inventory" not in page.url, "Should not log in with wrong password"',
                ]
                t3 = Task(id="1.3", text="Negative: wrong password should not log in")
                t3.steps = code3  # type: ignore[attr-defined]
                tasks.append(t3)

        if not tasks:
            # Generic fallback: produce at least a smoke test
            url = snapshot_data["url"] if snapshot_data else "about:blank"
            t = Task(id="1.1", text=f"Smoke: page loads without error — {intent}")
            t.steps = [
                f'page.goto({repr(url)})',
                f'assert page.title(), "Page should have a title"',
            ]
            tasks.append(t)

        return tasks

    def _render_proposal(self, intent: str, relevant, snapshot_data) -> str:
        lines = [f"# Proposal: {intent}", "", "## Why", "", f"User requested: {intent}", "",
                 "## Scope", ""]
        if snapshot_data:
            lines.append(f"- Target URL: `{snapshot_data['url']}`")
            lines.append(f"- Page title: `{snapshot_data['title']}`")
            lines.append(f"- Discovered {len(snapshot_data['elements'])} interactive elements")
        lines += ["", "## Knowledge consulted", ""]
        if relevant:
            for k in relevant:
                lines.append(f"- `{k.id}` ({k.type}, scope={k.scope}) — {k.title}")
        else:
            lines.append("_No prior knowledge found — this is exploratory._")
        return "\n".join(lines)

    def _render_design(self, intent: str, snapshot_data, tasks) -> str:
        lines = ["# Design", "", "## Approach", "",
                 "Use Playwright (Python) sync API. Default headless.",
                 "Each task is one independent test function.", "",
                 "## Tasks", ""]
        for t in tasks:
            lines.append(f"### {t.id} {t.text}")
            steps = getattr(t, "steps", [])
            if steps:
                lines.append("```python")
                lines.extend(steps)
                lines.append("```")
            lines.append("")
        return "\n".join(lines)

    def _write_change(self, change: Change) -> None:
        d = self.ws.get_change_dir(change.id)
        (d / "proposal.md").write_text(change.proposal)
        (d / "design.md").write_text(change.design)

        # tasks.md
        tasks_lines = [f"# Tasks: {change.title}", ""]
        for t in change.tasks:
            mark = "x" if t.done else " "
            tasks_lines.append(f"- [{mark}] **{t.id}** {t.text}")
        (d / "tasks.md").write_text("\n".join(tasks_lines))

        # change.json (machine-readable)
        ch_dict = to_dict(change)
        # Also persist tasks' .steps (dynamically added)
        for i, t in enumerate(change.tasks):
            if hasattr(t, "steps"):
                ch_dict["tasks"][i]["steps"] = t.steps  # type: ignore[attr-defined]
        (d / "change.json").write_text(json.dumps(ch_dict, indent=2, ensure_ascii=False))

    # =====================
    # run
    # =====================
    def cmd_run(self, change_id: Optional[str] = None, *, headed: bool = False) -> dict:
        if not self.ws.exists():
            return {"ok": False, "msg": "Workspace not initialized."}

        # Find the latest change if none was specified
        if change_id is None:
            changes = self.ws.list_changes()
            if not changes:
                return {"ok": False, "msg": "No changes found.", "next": f"{CLI} plan <project> \"<intent>\""}
            change_id = sorted(changes)[-1]

        change = self._read_change(change_id)
        if change is None:
            return {"ok": False, "msg": f"Change not found: {change_id}"}

        runner = registry.get_runner(language="python")

        # Render → tests/specs/
        test_path = runner.render(change, self.ws.tests_dir / "specs")

        # Execute
        run = runner.execute(test_path, headed=headed)
        run.change_id = change_id

        # Persist the run
        runs_dir = self.ws.get_change_dir(change_id) / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / f"{run.id}.json").write_text(
            json.dumps(to_dict(run), indent=2, ensure_ascii=False)
        )

        # Render the report
        reporter = registry.get_reporter("markdown")
        report_path = reporter.render(run, change, "markdown", self.ws.reports_dir)

        # Update change.runs
        change.runs.append(run.id)
        if run.status == "pass":
            for t in change.tasks:
                t.done = True
            change.status = "done"
        self._write_change(change)

        # Auto-review (post_turn)
        try:
            reviewer = registry.get_reviewer("post_turn")
            new_k = reviewer.review({
                "workspace_path": self.ws.root,
                "recent_runs": [run],
                "recent_changes": [change],
            })
            for k in new_k:
                self._save_project_knowledge(k)
        except Exception as e:
            print(f"Warning: post-turn review failed: {e}", file=sys.stderr)
            new_k = []

        return {
            "ok": True,
            "run_id": run.id,
            "status": run.status,
            "test_path": str(test_path),
            "report": str(report_path),
            "findings": len(run.findings),
            "knowledge_added": [k.id for k in new_k],
        }

    def _read_change(self, change_id: str) -> Optional[Change]:
        d = self.ws.get_change_dir(change_id)
        cj = d / "change.json"
        if not cj.exists():
            return None
        data = json.loads(cj.read_text())
        # Lightweight deserialization (dict-like, no nested dataclasses)
        tasks = []
        for t in data.get("tasks", []):
            task = Task(id=t["id"], text=t["text"], done=t.get("done", False))
            if "steps" in t:
                task.steps = t["steps"]  # type: ignore[attr-defined]
            tasks.append(task)
        change = Change(
            id=data["id"], title=data["title"],
            proposal=data.get("proposal", ""), design=data.get("design", ""),
            tasks=tasks, status=data.get("status", "ready"),
            created_at=data.get("created_at", ""),
            runs=data.get("runs", []),
        )
        return change

    # =====================
    # learn  (manual deep retrospective trigger)
    # =====================
    def cmd_learn(self) -> dict:
        if not self.ws.exists():
            return {"ok": False, "msg": "Workspace not initialized."}

        # Gather all changes and runs
        changes = []
        runs = []
        for cid in self.ws.list_changes():
            ch = self._read_change(cid)
            if ch:
                changes.append(ch)
                runs_dir = self.ws.get_change_dir(cid) / "runs"
                if runs_dir.exists():
                    for rj in runs_dir.glob("*.json"):
                        try:
                            data = json.loads(rj.read_text())
                            runs.append(Run(
                                id=data["id"], change_id=data.get("change_id", cid),
                                started_at=data.get("started_at", ""),
                                ended_at=data.get("ended_at", ""),
                                status=data.get("status", "blocked"),
                                executor=data.get("executor", ""),
                                test_path=data.get("test_path", ""),
                                headed=data.get("headed", False),
                                findings=[],  # simplified
                                notes=data.get("notes", ""),
                            ))
                        except Exception:
                            pass

        reviewer = registry.get_reviewer("post_turn")
        new_k = reviewer.review({
            "workspace_path": self.ws.root,
            "recent_runs": runs,
            "recent_changes": changes,
        })
        for k in new_k:
            self._save_project_knowledge(k)

        # Update insights.md (accumulated opinions)
        self._append_insight(
            f"Learn pass at {datetime.utcnow().isoformat()}: "
            f"reviewed {len(changes)} changes, {len(runs)} runs, "
            f"derived {len(new_k)} new knowledge items."
        )

        # v1.0: also run curator (apply mode) at the end of `learn`
        curator_summary = None
        try:
            from . import curator as C
            roots = self._curator_roots()
            brief_dir = self.ws.root / "_meta"
            cr = C.run_curator(roots, dry_run=False, brief_dir=brief_dir)
            curator_summary = {
                "scanned": cr.scanned,
                "transitioned": cr.transitioned,
                "by_transition": cr.by_transition,
                "brief": cr.brief_path,
            }
        except Exception as e:
            print(f"Warning: curator pass failed: {e}", file=sys.stderr)

        return {
            "ok": True,
            "changes_reviewed": len(changes),
            "runs_reviewed": len(runs),
            "knowledge_added": [k.id for k in new_k],
            "curator": curator_summary,
        }

    def _append_insight(self, text: str) -> None:
        existing = self.ws.insights_path.read_text() if self.ws.insights_path.exists() else "# Project Insights\n\n"
        new = existing + f"\n- {text}\n"
        self.ws.insights_path.write_text(new)

    # =====================
    # status
    # =====================
    def cmd_status(self) -> dict:
        if not self.ws.exists():
            return {"ok": False, "msg": f"Workspace does not exist: {self.ws.root}"}
        cfg = self.ws.read_config()
        changes = self.ws.list_changes()
        # Count knowledge entries
        n_digest = len(list(self.ws.digest_dir.glob("*.md"))) if self.ws.digest_dir.exists() else 0
        n_specs = len(list(self.ws.specs_dir.rglob("*.md"))) if self.ws.specs_dir.exists() else 0
        n_reports = len(list(self.ws.reports_dir.glob("*.md"))) if self.ws.reports_dir.exists() else 0

        return {
            "ok": True,
            "project": cfg.name,
            "url": cfg.url,
            "industry": cfg.industry,
            "language": cfg.language,
            "changes": changes,
            "digest_files": n_digest,
            "spec_files": n_specs,
            "report_files": n_reports,
            "workspace": str(self.ws.root),
        }

    # =========================================================
    # v1.0 — Atom-driven execution (Phase 3)
    # =========================================================
    def cmd_run_v1(self, change_id: Optional[str] = None, *,
                   headed: bool = False, dry_run: bool = False,
                   auto_yes: bool = False) -> dict:
        """Drive a plan as Atoms through RetryDriver + Watchdog.

        Falls back to legacy cmd_run if no atom_plan is found in change.json.
        """
        from .atoms import Atom, ExecutionContext
        from .retry import RetryPolicy, RetryStats, RetryDriver
        from .watchdog import make_step_watchdog, TotalRunWatchdog
        from .attribution import attribute_run
        import time as _t

        if not self.ws.exists():
            return {"ok": False, "msg": "Workspace not initialized."}

        if change_id is None:
            changes = self.ws.list_changes()
            if not changes:
                return {"ok": False, "msg": "No changes.", "next": f"{CLI} plan <project> \"<intent>\""}
            change_id = sorted(changes)[-1]
        change = self._read_change(change_id)
        if change is None:
            return {"ok": False, "msg": f"Change not found: {change_id}"}

        # Look for atom_plan in change.json (v1.0 format)
        change_dir = self.ws.get_change_dir(change_id)
        cj = json.loads((change_dir / "change.json").read_text())
        atom_plan_raw = cj.get("atom_plan", [])
        if not atom_plan_raw:
            # No v1.0 atom plan — fall back to legacy
            return self.cmd_run(change_id, headed=headed)

        atoms = []
        for i, a in enumerate(atom_plan_raw):
            atom = Atom.from_dict(a) if isinstance(a, dict) else a
            if not atom.step_id:
                atom.step_id = f"s{i+1}"
            atoms.append(atom)

        if dry_run:
            return {
                "ok": True, "dry_run": True, "change_id": change_id,
                "would_run": [
                    {"step_id": a.step_id, "atom": a.name,
                     "target": a.target, "value": a.value,
                     "description": a.description}
                    for a in atoms
                ],
            }

        run_id = f"run-{int(_t.time())}"
        ev_dir = change_dir / "runs" / run_id / "evidence"
        ev_dir.mkdir(parents=True, exist_ok=True)

        # --- Set up executor ---
        try:
            from ..adapters.executors.playwright_atoms import PlaywrightAtomExecutor
        except ImportError as e:
            return {"ok": False, "msg": f"Playwright executor unavailable: {e}"}

        ctx = ExecutionContext(
            run_id=run_id, project=self.ws.project,
            evidence_dir=str(ev_dir), timeout_ms=30000, headed=headed,
        )
        ex = PlaywrightAtomExecutor(headless=not headed)
        ex.setup(ctx)

        policy = RetryPolicy()
        stats = RetryStats()
        total_wd = TotalRunWatchdog(timeout_s=policy.total_run_timeout_s)
        total_wd.start()
        step_call = make_step_watchdog(
            ex, default_timeout_s=policy.per_step_timeout_s,
            evidence_dir=str(ev_dir), mode="soft",
        )
        drv = RetryDriver(ex, policy, stats, watchdog_call=step_call)

        outcomes = []
        aborted_reason = None
        started_at = datetime.utcnow().isoformat()
        try:
            for atom in atoms:
                if total_wd.tripped():
                    aborted_reason = "total_run_timeout"
                    (ev_dir / "_run_aborted.json").write_text(json.dumps({
                        "run_id": run_id, "reason": aborted_reason,
                        "aborted_before_step": atom.step_id,
                        "completed_steps": len(outcomes),
                        "planned_steps": len(atoms),
                    }, indent=2))
                    break
                if stats.case_budget_exhausted:
                    aborted_reason = "case_budget_exhausted"
                    break
                outcomes.append(drv.run_atom(atom, ctx))
        finally:
            total_wd.stop()
            try:
                ex.teardown(ctx)
            except Exception:
                pass

        verdict = attribute_run(
            outcomes,
            total_timeout_tripped=(aborted_reason == "total_run_timeout"),
            case_budget_exhausted=stats.case_budget_exhausted,
        )

        # Persist run record
        run_record = {
            "id": run_id, "change_id": change_id,
            "started_at": started_at,
            "ended_at": datetime.utcnow().isoformat(),
            "status": verdict.verdict,
            "verdict_reasons": verdict.reasons,
            "drifted_selectors": verdict.drifted_selectors,
            "failed_steps": verdict.failed_steps,
            "aborted_reason": aborted_reason,
            "stats": {
                "physical_attempts": stats.physical_attempts,
                "heals_attempted": stats.heals_attempted,
                "heals_succeeded": stats.heals_succeeded,
                "case_budget_used": stats.case_budget_used,
                "case_budget_exhausted": stats.case_budget_exhausted,
            },
            "steps": [
                {
                    "step_id": o.atom.step_id,
                    "atom": o.atom.name,
                    "target": o.atom.target,
                    "value": o.atom.value,
                    "description": o.atom.description,
                    "ok": o.final_result.ok,
                    "attempts": o.attempts,
                    "heals": o.heals,
                    "healed_with": o.healed_with.target if o.healed_with else None,
                    "error_kind": o.final_result.error_kind,
                    "error_msg": o.final_result.error_msg,
                    "wall_ms": o.final_result.wall_ms,
                    "screenshot": o.final_result.screenshot_path,
                }
                for o in outcomes
            ],
        }
        (change_dir / "runs" / f"{run_id}.json").write_text(
            json.dumps(run_record, indent=2, ensure_ascii=False))

        # Update change
        change.runs.append(run_id)
        if verdict.verdict == "pass":
            for t in change.tasks:
                t.done = True
            change.status = "done"
        self._write_change(change)

        # v1.1: Emit result.ctrf.json (CTRF v1.0 data layer).
        # Failures here NEVER break the run flow — same async-bypass
        # rule as RunBus sidecars.
        ctrf_info = None
        try:
            from .reporting.integration import emit_ctrf_for_run
            ctrf_info = emit_ctrf_for_run(
                change_dir=change_dir,
                run_record_path=change_dir / "runs" / f"{run_id}.json",
                run_id=run_id,
                project=self.ws.project,
            )
        except Exception as e:
            print(f"Warning: CTRF emit failed: {e}", file=sys.stderr)

        # v1.0: Auto-render report
        report_info = None

        # v1.0.2: publish run.completed to RunBus (async sidecar).
        # Failures here NEVER affect the user-facing return value.
        try:
            from .events import RunCompleted
            from .run_bus import RunBus
            from .sinks.runner import spawn_inline
            bus = RunBus(self.ws.brain_dir)
            bus.publish(RunCompleted(
                project=self.ws.project,
                change_id=change_id,
                run_id=run_id,
                verdict=verdict.verdict,
                build="",  # populated when doctor learns to detect builds
                run_record_path=str(change_dir / "runs" / f"{run_id}.json"),
                evidence_dir=str(ev_dir),
                test_file_path="",  # populated when plan->spec mapping lands
                duration_ms=int(stats.get("wall_ms", 0)
                                if isinstance(stats, dict) else 0),
            ))
            # Best-effort: kick a subprocess to drain. Fire-and-forget.
            spawn_inline(self.ws.brain_dir)
        except Exception as e:
            print(f"Warning: bus publish failed: {e}", file=sys.stderr)

        return {
            "ok": verdict.verdict == "pass",
            "run_id": run_id,
            "change_id": change_id,
            "verdict": verdict.verdict,
            "reasons": verdict.reasons,
            "stats": run_record["stats"],
            "evidence_dir": str(ev_dir),
            "report": report_info,
            "report_hint": f"{CLI} report {self.ws.project} {run_id}",
        }

    # =========================================================
    # v1.0 — stubs for new commands (filled in later phases)
    # =========================================================
    def cmd_design(self, feature: str) -> dict:
        return {"ok": False, "msg": "design: not yet implemented (Phase 5)",
                "feature": feature}

    def cmd_explore(self, charter: str, *, timebox: int = 30) -> dict:
        return {"ok": False, "msg": "explore: not yet implemented (Phase 5)",
                "charter": charter, "timebox_min": timebox}

    def cmd_report(self, run_id: str) -> dict:
        """Render HTML report for a past run.

        v1.1: HTML is now a view over `result.ctrf.json` when present;
        falls back to legacy run-record-only rendering for older runs.
        """
        if not self.ws.exists():
            return {"ok": False, "msg": "Workspace not initialized."}
        # Locate the run record across all changes
        for cid in self.ws.list_changes():
            run_path = self.ws.get_change_dir(cid) / "runs" / f"{run_id}.json"
            if run_path.exists():
                return {"ok": True, "change_id": cid,
                        "msg": "HTML reporter removed; run record exists."}
        return {"ok": False, "msg": f"Run not found: {run_id}"}

    def cmd_heal(self, run_id: str, *, auto_yes: bool = False) -> dict:
        return {"ok": False, "msg": "heal: not yet implemented (Phase 5)",
                "run_id": run_id}

    def cmd_revive(self, knowledge_id: str) -> dict:
        """Lift one entry's state back up + log the revival event."""
        from . import curator as C
        if not self.ws.exists():
            return {"ok": False, "msg": "Workspace not initialized."}
        roots = self._curator_roots()
        result = C.revive_entry(knowledge_id, roots,
                                by="manual revive",
                                note=f"by user in {self.ws.project}",
                                dry_run=False)
        return result

    # =========================================================
    # v1.0.2 — Scheduler entry points (trigger jobs explicitly)
    # =========================================================

    def cmd_curate(self, *, force: bool = False) -> dict:
        """Run the brain CuratorJob (apply state transitions).

        By default respects the job's RUN_EVERY_HOURS throttle; pass
        force=True to bypass (useful for manual cleanup)."""
        if not self.ws.exists():
            return {"ok": False, "msg": "Workspace not initialized."}
        from .scheduler.curator_job import CuratorJob
        job = CuratorJob(self.ws.brain_dir)
        cur = job.load_cursor()
        if force:
            from datetime import datetime, timedelta
            # Pretend last_run was long ago to force should_run -> True
            old = (datetime.utcnow() - timedelta(days=7)).isoformat() + "Z"
            cur.last_run_at = old
            job.save_cursor(cur)
        result = job.execute()
        return {
            "ok": result.error is None,
            "ran": result.ran,
            "summary": result.summary,
            "error": result.error,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
        }

    def cmd_reflect(self, *, force: bool = False) -> dict:
        """Run the ReflectionJob (LLM stub for now). Writes proposal
        to brain/business/_proposed_<snap_id>.yml.

        force=True bypasses the run-count threshold."""
        if not self.ws.exists():
            return {"ok": False, "msg": "Workspace not initialized."}
        from .scheduler.reflection_job import ReflectionJob
        job = ReflectionJob(self.ws.brain_dir)
        cur = job.load_cursor()
        if force:
            cur.extra["forced_next"] = True
            job.save_cursor(cur)
        result = job.execute()
        return {
            "ok": result.error is None,
            "ran": result.ran,
            "summary": result.summary,
            "error": result.error,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
        }

    def cmd_drain(self) -> dict:
        """Synchronously drain the RunBus (for deferred mode / testing).
        Useful when running headless without subprocess spawning."""
        if not self.ws.exists():
            return {"ok": False, "msg": "Workspace not initialized."}
        from .run_bus import RunBus
        from .sinks.runner import process_backlog_once, default_sinks
        bus = RunBus(self.ws.brain_dir)
        summary = process_backlog_once(bus, default_sinks(self.ws.brain_dir))
        return {"ok": True, "summary": summary}

    def cmd_health(self) -> dict:
        """Knowledge curator dry-run + reverse-feedback bus visibility."""
        from . import curator as C
        if not self.ws.exists():
            return {"ok": False, "msg": "Workspace not initialized."}

        # --- Knowledge curator (existing) ---
        roots = self._curator_roots()
        brief_dir = self.ws.root / "_meta"
        report = C.run_curator(roots, dry_run=True, brief_dir=brief_dir)

        result = {
            "ok": True,
            "knowledge": {
                "scanned": report.scanned,
                "transitioned": report.transitioned,
                "by_transition": report.by_transition,
                "top_used": report.top_used,
                "newly_stale": [e["id"] for e in report.newly_stale],
                "newly_deprecated": [e["id"] for e in report.newly_deprecated],
                "newly_archived": [e["id"] for e in report.newly_archived],
                "promotion_candidates":
                    [c["id"] for c in report.promotion_candidates],
                "brief_path": report.brief_path,
                "dry_run": True,
            },
        }

        # --- Reverse-feedback bus (new in v1.0.2) ---
        try:
            from .run_bus import RunBus
            bus = RunBus(self.ws.brain_dir)
            result["reverse_bus"] = bus.stats()
            # Dead-letter listing
            dl_dir = bus.dead_letter_dir
            dl_files = []
            if dl_dir.exists():
                for p in sorted(dl_dir.glob("*.jsonl")):
                    try:
                        n_lines = sum(1 for _ in p.open())
                    except Exception:
                        n_lines = -1
                    dl_files.append({"sink": p.stem, "count": n_lines,
                                     "path": str(p)})
            result["reverse_bus"]["dead_letter"] = dl_files
        except Exception as e:
            result["reverse_bus"] = {"error": f"{type(e).__name__}: {e}"}

        # --- Scheduler jobs (new in v1.0.2) ---
        try:
            from .scheduler.curator_job import CuratorJob
            from .scheduler.reflection_job import ReflectionJob
            jobs = [CuratorJob(self.ws.brain_dir),
                    ReflectionJob(self.ws.brain_dir)]
            sched_info = []
            for job in jobs:
                cur = job.load_cursor()
                sched_info.append({
                    "name": job.name,
                    "needs_snapshot": job.needs_snapshot,
                    "last_run_at": cur.last_run_at,
                    "runs_seen": cur.runs_seen,
                    "success_count": cur.success_count,
                    "failure_count": cur.failure_count,
                    "should_run_now": job.should_run(cur),
                })
            result["scheduler"] = {"jobs": sched_info}
        except Exception as e:
            result["scheduler"] = {"error": f"{type(e).__name__}: {e}"}

        # --- Snapshots (latest 5) ---
        try:
            from .scheduler.snapshot import list_snapshots
            snaps = list_snapshots(self.ws.brain_dir)[:5]
            result["snapshots"] = [
                {"snap_id": s.snap_id, "upper_bound": s.upper_bound,
                 "taken_at": s.taken_at,
                 "evidence_run_count": s.evidence_run_count}
                for s in snaps
            ]
        except Exception as e:
            result["snapshots"] = {"error": f"{type(e).__name__}: {e}"}

        return result

    # =========================================================
    # v1.1 — CTRF validation + portable export
    # =========================================================

    def cmd_validate_ctrf(self, run_id: str, *, strict: bool = False) -> dict:
        """Validate `result.ctrf.json` for a past run.

        Locates the file across all changes; if missing, attempts to
        regenerate it from the run record on the fly.
        """
        from .reporting import validate_ctrf
        from .reporting.integration import emit_ctrf_for_run
        if not self.ws.exists():
            return {"ok": False, "msg": "Workspace not initialized."}

        for cid in self.ws.list_changes():
            change_dir = self.ws.get_change_dir(cid)
            run_record = change_dir / "runs" / f"{run_id}.json"
            ctrf_path = change_dir / "runs" / run_id / "result.ctrf.json"
            if not run_record.exists():
                continue
            # Regenerate CTRF if missing or older than the run record.
            try:
                regen = (
                    not ctrf_path.exists()
                    or ctrf_path.stat().st_mtime < run_record.stat().st_mtime
                )
            except Exception:
                regen = True
            if regen:
                emit_ctrf_for_run(
                    change_dir=change_dir,
                    run_record_path=run_record,
                    run_id=run_id,
                    project=self.ws.project,
                )
            if not ctrf_path.exists():
                return {
                    "ok": False,
                    "msg": f"CTRF document still missing after regen: {ctrf_path}",
                    "run_id": run_id,
                    "change_id": cid,
                }
            try:
                doc = json.loads(ctrf_path.read_text())
            except Exception as e:
                return {"ok": False, "msg": f"CTRF unreadable: {e}",
                        "ctrf_path": str(ctrf_path)}
            ok, errors, warnings = validate_ctrf(doc, strict=strict)
            return {
                "ok": ok,
                "run_id": run_id,
                "change_id": cid,
                "ctrf_path": str(ctrf_path),
                "strict": strict,
                "errors": errors,
                "warnings": warnings,
                "summary": doc.get("results", {}).get("summary", {}),
            }
        return {"ok": False, "msg": f"Run not found: {run_id}"}

    def cmd_export(self, fmt: str, *, out_dir: Optional[str] = None) -> dict:
        """Export brain or runs in a portable format.

        Formats
        -------
        - `mem0`: agent-memory portable JSON (one entry per brain item).
          Compatible with `mem0 import`.
        - `ctrf`: bundle every CTRF doc found across all runs.
        - `json` : raw brain dump (state + indices).
        """
        if not self.ws.exists():
            return {"ok": False, "msg": "Workspace not initialized."}
        from .reporting import portable_export
        try:
            return portable_export.export(
                workspace=self.ws,
                fmt=fmt,
                out_dir=Path(out_dir) if out_dir else None,
            )
        except Exception as e:
            return {"ok": False, "msg": f"export failed: {type(e).__name__}: {e}",
                    "fmt": fmt}

    def _curator_roots(self) -> list[Path]:
        """Knowledge directories the curator should walk for this project."""
        return [
            BUILTIN_KNOWLEDGE,
            self.ws.brain_dir,
            self.ws.specs_dir,
            self.ws.digest_dir,
        ]
