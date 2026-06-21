"""CTRF v1.0 builder + validator.

CTRF spec: https://ctrf.io
Schema (this skill's subset): assets/schemas/ctrf.schema.json

Design notes
------------
- We do NOT depend on jsonschema (external) — keep the skill stdlib-only.
  Validation is a small hand-rolled walk: enough to catch the four MUST
  requirements and structural mistakes.
- All Evo-QA-specific data lives under `extra.evoQa` (top
  level) or `tests[i].extra.*` per spec. We never invent top-level keys.
- Time fields: CTRF uses millisecond UNIX epochs for `start`/`stop`;
  we keep ISO 8601 strings only inside our `extra.evoQa.*` and
  inside attachment `extra.scriptGeneratedAt`.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CTRF_SPEC_VERSION = "1.0.0"
SKILL_GENERATED_BY = "evo-qa"

# Map our internal status vocabulary to CTRF v1.0 enum.
_STATUS_MAP = {
    "pass":  "passed",
    "passed": "passed",
    "ok": "passed",
    "fail": "failed",
    "failed": "failed",
    "error": "failed",
    "skip": "skipped",
    "skipped": "skipped",
    "pending": "pending",
    "system_failure": "other",   # NOT failed — environment issue
    "infra_failure": "other",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_to_epoch_ms(s: Optional[str]) -> int:
    """Parse ISO 8601 → epoch ms. Returns 0 on failure (CTRF tolerates 0)."""
    if not s:
        return 0
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return 0


def _map_status(s: Optional[str]) -> str:
    if not s:
        return "other"
    return _STATUS_MAP.get(str(s).lower(), "other")


class CtrfValidationError(ValueError):
    """Raised when a CTRF document violates the v1.0 contract."""


# ---------- Builder ----------

def build_ctrf(
    *,
    run_record: Dict[str, Any],
    project: str,
    skill_version: str,
    test_scripts: Optional[List[Dict[str, Any]]] = None,
    prompt_history: Optional[List[Dict[str, Any]]] = None,
    ai_diagnoses: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Convert a Evo QA run record into a CTRF v1.0 document.

    Parameters
    ----------
    run_record : dict
        The contents of `<change>/runs/<run-id>.json` (as produced by
        Orchestrator). Must contain at minimum `id`, `status` (or
        `verdict`), `started_at`, `ended_at`, and a list of `outcomes`
        (or `steps`).
    project : str
        Project name (the workspace name).
    skill_version : str
        Evo QA skill version (from SKILL.md metadata).
    test_scripts : list of dict, optional
        Generated test artifacts to attach. Each item:
            {
              "name": "test_login.py",
              "path": "absolute/or/workspace-relative/path",
              "content_type": "text/x-python" | "text/javascript",
              "generated_at": "ISO8601",  # REQUIRED by spec
              "step_id": "s001"  # optional; if set, attaches to that test
            }
    prompt_history : list of dict, optional
        User/assistant prompts that produced this run. Each entry:
            {"timestamp": ISO8601, "role": "user|assistant|system",
             "content": str}
    ai_diagnoses : dict, optional
        Map of step_id (or test name) → AI-generated paragraph. Lands in
        `tests[i].ai`.

    Returns
    -------
    dict — a CTRF v1.0 document (not yet validated; call
    `validate_ctrf` to enforce the contract).
    """
    test_scripts = test_scripts or []
    prompt_history = prompt_history or []
    ai_diagnoses = ai_diagnoses or {}

    started = run_record.get("started_at") or run_record.get("start") or ""
    ended = run_record.get("ended_at") or run_record.get("stop") or ""
    start_ms = _iso_to_epoch_ms(started)
    stop_ms = _iso_to_epoch_ms(ended)

    # --- tests[]
    outcomes = (
        run_record.get("outcomes")
        or run_record.get("steps")
        or []
    )
    tests: List[Dict[str, Any]] = []
    counts = {"passed": 0, "failed": 0, "pending": 0, "skipped": 0, "other": 0}

    for i, o in enumerate(outcomes):
        step_id = o.get("step_id") or f"step-{i:03d}"
        name = o.get("description") or o.get("atom") or step_id
        ok = o.get("ok")
        if ok is True:
            status = "passed"
        elif ok is False:
            status = "failed"
        else:
            status = _map_status(o.get("status") or o.get("verdict"))
        counts[status] = counts.get(status, 0) + 1

        wall_ms = int(o.get("wall_ms") or o.get("duration_ms") or 0)

        test: Dict[str, Any] = {
            "name": str(name),
            "status": status,
            "duration": wall_ms,
        }
        # Optional fields, populated only when present
        if o.get("error_msg"):
            test["message"] = str(o["error_msg"])
        if o.get("error_kind"):
            test["rawStatus"] = str(o["error_kind"])
        if o.get("attempts") is not None:
            test["retries"] = max(0, int(o["attempts"]) - 1)
        if o.get("heals"):
            test["flaky"] = True
        if o.get("screenshot"):
            test["screenshot"] = str(o["screenshot"])

        # AI diagnosis (CTRF native field)
        diag = ai_diagnoses.get(step_id) or ai_diagnoses.get(str(name))
        if diag:
            test["ai"] = diag

        # Attachments: scripts whose step_id matches go on this test
        attachments: List[Dict[str, Any]] = []
        for s in test_scripts:
            if s.get("step_id") and s["step_id"] == step_id:
                attachments.append(_make_attachment(s))
        if attachments:
            test["attachments"] = attachments

        # Step-level extra
        extra: Dict[str, Any] = {}
        if o.get("healed_with"):
            extra["healedWith"] = o["healed_with"]
        if o.get("target"):
            extra["target"] = o["target"]
        if extra:
            test["extra"] = extra

        tests.append(test)

    # Scripts not bound to a step → synthesize a "test" entry per script
    # so the attachment isn't lost.
    unbound = [s for s in test_scripts if not s.get("step_id")]
    for s in unbound:
        tests.append({
            "name": f"(generated script) {s.get('name', 'unnamed')}",
            "status": "other",
            "duration": 0,
            "type": "generated",
            "attachments": [_make_attachment(s)],
        })
        counts["other"] += 1

    summary = {
        "tests": len(tests),
        "passed": counts.get("passed", 0),
        "failed": counts.get("failed", 0),
        "pending": counts.get("pending", 0),
        "skipped": counts.get("skipped", 0),
        "other": counts.get("other", 0),
        "start": start_ms,
        "stop": stop_ms,
    }

    doc: Dict[str, Any] = {
        "reportFormat": "CTRF",
        "specVersion": CTRF_SPEC_VERSION,
        "reportId": run_record.get("id") or f"run-{uuid.uuid4().hex[:12]}",
        "timestamp": _now_iso(),
        "generatedBy": SKILL_GENERATED_BY,
        "results": {
            "tool": {
                "name": SKILL_GENERATED_BY,
                "version": skill_version,
            },
            "summary": summary,
            "tests": tests,
            "environment": {
                "appName": project,
                "buildName": run_record.get("build", "") or "",
            },
        },
        "extra": {
            "evoQa": {
                "schemaVersion": "1.0",
                "skillVersion": skill_version,
                "promptHistory": prompt_history,
                "runRecordRef": run_record.get("id", ""),
                "verdict": run_record.get("verdict")
                            or run_record.get("status")
                            or "unknown",
            },
        },
    }
    return doc


def _make_attachment(s: Dict[str, Any]) -> Dict[str, Any]:
    """Build a CTRF attachment from a test_scripts entry."""
    name = s.get("name") or os.path.basename(s.get("path", "")) or "script"
    ct = s.get("content_type")
    if not ct:
        # Infer from extension
        ext = (Path(name).suffix or "").lower()
        ct = {
            ".py": "text/x-python",
            ".js": "text/javascript",
            ".ts": "text/typescript",
            ".sh": "text/x-shellscript",
        }.get(ext, "text/plain")
    att: Dict[str, Any] = {
        "name": name,
        "contentType": ct,
        "path": str(s.get("path", "")),
    }
    extra: Dict[str, Any] = {}
    gen_at = s.get("generated_at")
    if gen_at:
        extra["scriptGeneratedAt"] = gen_at
    if s.get("language"):
        extra["language"] = s["language"]
    if extra:
        att["extra"] = extra
    return att


# ---------- Validator ----------

# The four MUST requirements (Evo QA contract on top of CTRF v1.0).
# These produce hard errors. Lesser issues become warnings.

REQUIRED_TOP = ["results"]
REQUIRED_RESULTS = ["tool", "summary", "tests"]
REQUIRED_SUMMARY = ["tests", "passed", "failed", "pending", "skipped",
                    "other", "start", "stop"]
ALLOWED_STATUSES = {"passed", "failed", "skipped", "pending", "other"}

EQ_MUST_HAVE_PROMPT_HISTORY = "extra.evoQa.promptHistory"
PQ_MUST_HAVE_AI_FOR_FAILURES = "tests[i].ai when tests[i].status == 'failed'"
PQ_MUST_HAVE_SCRIPT_TIMESTAMPS = (
    "tests[i].attachments[j].extra.scriptGeneratedAt for every script attachment"
)


def validate_ctrf(
    doc: Dict[str, Any],
    *,
    strict: bool = True,
) -> Tuple[bool, List[str], List[str]]:
    """Validate a CTRF document against the v1.0 + Evo QA contract.

    Parameters
    ----------
    doc : dict
        The CTRF document to validate.
    strict : bool
        If True (default), the four Evo-QA-specific MUSTs become
        errors. If False, they become warnings (useful for legacy run
        records that pre-date v1.1).

    Returns
    -------
    (ok, errors, warnings)
        ok=True iff errors is empty. The doc is "valid" iff ok.
    """
    errors: List[str] = []
    warnings: List[str] = []

    # --- structural
    if not isinstance(doc, dict):
        return False, ["doc is not an object"], []
    for k in REQUIRED_TOP:
        if k not in doc:
            errors.append(f"missing top-level key: {k}")
    if doc.get("reportFormat") and doc["reportFormat"] != "CTRF":
        errors.append(f"reportFormat must be 'CTRF', got {doc['reportFormat']!r}")

    results = doc.get("results")
    if not isinstance(results, dict):
        errors.append("results must be an object")
        return False, errors, warnings

    for k in REQUIRED_RESULTS:
        if k not in results:
            errors.append(f"missing results.{k}")

    # tool
    tool = results.get("tool", {})
    if not isinstance(tool, dict) or not tool.get("name"):
        errors.append("results.tool.name is required")

    # summary
    summary = results.get("summary", {})
    if not isinstance(summary, dict):
        errors.append("results.summary must be an object")
    else:
        for k in REQUIRED_SUMMARY:
            if k not in summary:
                errors.append(f"missing results.summary.{k}")
        # counts must be non-negative ints
        for k in ("tests", "passed", "failed", "pending", "skipped", "other"):
            v = summary.get(k)
            if v is not None and (not isinstance(v, int) or v < 0):
                errors.append(f"results.summary.{k} must be non-negative int, got {v!r}")

    # tests
    tests = results.get("tests", [])
    if not isinstance(tests, list):
        errors.append("results.tests must be an array")
        tests = []
    else:
        # summary.tests must equal len(tests) when both present
        if isinstance(summary, dict) and isinstance(summary.get("tests"), int):
            if summary["tests"] != len(tests):
                errors.append(
                    f"results.summary.tests ({summary['tests']}) != "
                    f"len(results.tests) ({len(tests)})"
                )
        for i, t in enumerate(tests):
            if not isinstance(t, dict):
                errors.append(f"tests[{i}] is not an object")
                continue
            for k in ("name", "status", "duration"):
                if k not in t:
                    errors.append(f"tests[{i}] missing {k}")
            if t.get("status") not in ALLOWED_STATUSES and "status" in t:
                errors.append(
                    f"tests[{i}].status invalid: {t['status']!r} "
                    f"(allowed: {sorted(ALLOWED_STATUSES)})"
                )

    # --- Evo QA contract (the four MUSTs)
    pq_errors: List[str] = []
    pq_warnings: List[str] = []

    extra = doc.get("extra") or {}
    pq = (extra.get("evoQa") if isinstance(extra, dict) else None) or {}

    # 1. promptHistory present (can be empty, but must exist)
    if "promptHistory" not in pq:
        pq_errors.append(
            f"missing {EQ_MUST_HAVE_PROMPT_HISTORY} "
            f"(see SKILL.md 'STRICT REQUIREMENTS — Reports')"
        )
    elif not isinstance(pq["promptHistory"], list):
        pq_errors.append(f"{EQ_MUST_HAVE_PROMPT_HISTORY} must be an array")

    # 2. AI diagnosis on every failed test
    for i, t in enumerate(tests):
        if isinstance(t, dict) and t.get("status") == "failed":
            if not t.get("ai"):
                pq_errors.append(
                    f"tests[{i}] failed but has no `ai` field "
                    f"(every failure needs an AI diagnosis)"
                )

    # 3. Every attachment that is a script must carry a generation timestamp
    script_cts = {"text/x-python", "text/javascript", "text/typescript"}
    for i, t in enumerate(tests):
        if not isinstance(t, dict):
            continue
        for j, a in enumerate(t.get("attachments") or []):
            if not isinstance(a, dict):
                continue
            ct = a.get("contentType", "")
            if ct in script_cts:
                ex = a.get("extra") or {}
                if not (isinstance(ex, dict) and ex.get("scriptGeneratedAt")):
                    pq_errors.append(
                        f"tests[{i}].attachments[{j}] is a script ({ct}) "
                        f"but missing extra.scriptGeneratedAt"
                    )

    # 4. (Test scripts presence) — soft warning only. A run with zero
    # generated scripts is legitimate (e.g. exploratory session).
    has_any_script = any(
        isinstance(a, dict) and a.get("contentType", "") in script_cts
        for t in tests if isinstance(t, dict)
        for a in (t.get("attachments") or [])
    )
    if not has_any_script:
        pq_warnings.append(
            "No script attachments found. If this run generated tests, "
            "they should be attached (text/x-python / text/javascript)."
        )

    if strict:
        errors.extend(pq_errors)
        warnings.extend(pq_warnings)
    else:
        warnings.extend(pq_errors + pq_warnings)

    return (len(errors) == 0), errors, warnings
