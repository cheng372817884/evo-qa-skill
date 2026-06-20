"""Orchestrator-side glue: gather signals from the workspace and write
`result.ctrf.json` next to a finished run.

Why a separate module?
- Keeps `orchestrator.py` from gaining yet another import block.
- Makes the data-collection contract testable in isolation.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .writer import write_ctrf_for_run

PROMPTS_FILE_NAME = "prompts.jsonl"


def _read_skill_version() -> str:
    """Best-effort: parse SKILL.md frontmatter for `version`."""
    here = Path(__file__).resolve()
    # evo-qa/evo_qa/core/reporting/integration.py
    # parents[3] == evo-qa/
    skill_md = here.parents[3] / "SKILL.md"
    if not skill_md.exists():
        return "unknown"
    try:
        text = skill_md.read_text()
        # Crude YAML scan — we only need the version line and want zero deps.
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("version:"):
                v = s.split(":", 1)[1].strip().strip('"').strip("'")
                return v
    except Exception:
        pass
    return "unknown"


def _gather_prompt_history(change_dir: Path) -> List[Dict[str, Any]]:
    """Return the JSONL prompt log if the user/client has been writing one.

    The contract: callers append one JSON object per line to
    `<change>/prompts.jsonl`, each with fields {timestamp, role, content}.

    Backwards-compat: if missing or unparseable, return [] (the validator
    in non-strict mode will emit a warning, not an error).
    """
    p = change_dir / PROMPTS_FILE_NAME
    if not p.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "content" in obj:
                    obj.setdefault("timestamp", "")
                    obj.setdefault("role", "user")
                    out.append(obj)
            except json.JSONDecodeError:
                continue
    except Exception:
        return []
    return out


def _gather_test_scripts(change_dir: Path) -> List[Dict[str, Any]]:
    """Return descriptors for any generated test scripts found in the
    change directory.

    Heuristic v1.1.0:
    - Anything matching `test_*.py` / `*.spec.py` / `*.spec.js` /
      `*.spec.ts` directly inside the change dir.
    - generated_at = file mtime, ISO 8601.
    - step_id is left unset; the writer will surface them as standalone
      "(generated script) X" entries unless callers wire them up.
    """
    if not change_dir.exists():
        return []
    patterns = ["test_*.py", "*.spec.py", "*.spec.js", "*.spec.ts"]
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for pat in patterns:
        for p in change_dir.glob(pat):
            if p in seen:
                continue
            seen.add(p)
            ext = p.suffix.lower()
            ct = {
                ".py": "text/x-python",
                ".js": "text/javascript",
                ".ts": "text/typescript",
            }.get(ext, "text/plain")
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            out.append({
                "name": p.name,
                "path": str(p),
                "content_type": ct,
                "generated_at": mtime.strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
    return out


def _gather_ai_diagnoses(change_dir: Path, run_id: str) -> Dict[str, str]:
    """Look for a sibling `<run-id>.ai.json` file produced by an LLM hook.

    Format: { "step-001": "diagnosis paragraph", "step-002": "..." }
    """
    p = change_dir / "runs" / f"{run_id}.ai.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if v}
    except Exception:
        pass
    return {}


def emit_ctrf_for_run(
    *,
    change_dir: Path,
    run_record_path: Path,
    run_id: str,
    project: str,
    out_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """High-level entry point used by the orchestrator.

    Default `out_dir` is `<change>/runs/<run_id>/` (creates it if needed).
    Result document lands at `<out_dir>/result.ctrf.json`.

    Returns the dict from write_ctrf_for_run, or {"ok": False, "msg": ...}
    on unexpected failure (CTRF emission must NEVER break the user-facing
    run flow — same rule as RunBus sidecars).
    """
    try:
        if out_dir is None:
            out_dir = Path(change_dir) / "runs" / run_id
        scripts = _gather_test_scripts(change_dir)
        prompts = _gather_prompt_history(change_dir)
        ai = _gather_ai_diagnoses(change_dir, run_id)
        skill_version = _read_skill_version()

        return write_ctrf_for_run(
            run_record_path=Path(run_record_path),
            out_dir=Path(out_dir),
            project=project,
            skill_version=skill_version,
            test_scripts=scripts,
            prompt_history=prompts,
            ai_diagnoses=ai,
            strict=False,
        )
    except Exception as e:
        return {"ok": False, "msg": f"CTRF emit failed: {e}"}
