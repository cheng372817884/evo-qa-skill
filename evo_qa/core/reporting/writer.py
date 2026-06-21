"""Glue: take a Evo QA run record on disk → emit result.ctrf.json.

This is the entry point invoked by the orchestrator after `cmd_run`
finishes (and by the `cli ctrf` subcommand for offline regeneration).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ctrf import build_ctrf, validate_ctrf, CtrfValidationError


def write_ctrf_for_run(
    *,
    run_record_path: Path,
    out_dir: Path,
    project: str,
    skill_version: str,
    test_scripts: Optional[List[Dict[str, Any]]] = None,
    prompt_history: Optional[List[Dict[str, Any]]] = None,
    ai_diagnoses: Optional[Dict[str, str]] = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """Render a `result.ctrf.json` next to a run record.

    Layout produced
    ---------------
    out_dir/
    ├── result.ctrf.json   ← this function's output
    └── (whatever else the caller writes)

    Parameters
    ----------
    run_record_path : Path
        Path to `<change>/runs/<run-id>.json`.
    out_dir : Path
        Where to write `result.ctrf.json`. Will be created if missing.
    project, skill_version : str
        Forwarded to build_ctrf.
    test_scripts, prompt_history, ai_diagnoses :
        Forwarded to build_ctrf.
    strict : bool
        If True, validation errors RAISE CtrfValidationError. If False
        (default for now), errors are still written into the doc's
        `extra.evoQa.validation` field for visibility, but the
        function returns successfully.

    Returns
    -------
    dict — {"ok": bool, "ctrf_path": str, "errors": [...], "warnings": [...]}
    """
    run_record = json.loads(Path(run_record_path).read_text())

    doc = build_ctrf(
        run_record=run_record,
        project=project,
        skill_version=skill_version,
        test_scripts=test_scripts,
        prompt_history=prompt_history,
        ai_diagnoses=ai_diagnoses,
    )
    ok, errors, warnings = validate_ctrf(doc, strict=False)

    # Inject validation status into the doc itself for transparency.
    doc.setdefault("extra", {}).setdefault("evoQa", {})
    doc["extra"]["evoQa"]["validation"] = {
        "ok": ok,
        "errors": list(errors),
        "warnings": list(warnings),
        "validatedAt": datetime.now(timezone.utc)
                              .strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ctrf_path = out_dir / "result.ctrf.json"
    ctrf_path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=False)
    )

    if strict and errors:
        raise CtrfValidationError(
            f"CTRF validation failed for {run_record_path}: " +
            "; ".join(errors)
        )

    return {
        "ok": ok,
        "ctrf_path": str(ctrf_path),
        "errors": list(errors),
        "warnings": list(warnings),
    }
