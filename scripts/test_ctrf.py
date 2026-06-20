"""Test the CTRF data layer (build + validate + write).

Tested invariants
-----------------
T1   minimal happy path → valid CTRF
T2   failure WITHOUT `ai` → validation error
T3   failure WITH `ai` → valid
T4   script attachment WITHOUT `scriptGeneratedAt` → error
T5   script attachment WITH `scriptGeneratedAt` → valid
T6   empty promptHistory list is fine
T7   missing promptHistory key → error
T8   summary counts match tests array
T9   tests[i].status only takes allowed enum values
T10  write_ctrf_for_run produces a file on disk
T11  validation report is embedded in the written doc
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from evo_qa.core.reporting import (
    build_ctrf,
    validate_ctrf,
    write_ctrf_for_run,
    CTRF_SPEC_VERSION,
)


def _base_run(*, outcomes=None, run_id="run-test", verdict="pass"):
    return {
        "id": run_id,
        "started_at": "2026-06-18T10:00:00Z",
        "ended_at": "2026-06-18T10:01:00Z",
        "verdict": verdict,
        "outcomes": outcomes or [],
    }


def section(name):
    print(f"\n--- {name} ---")


def T1_minimal_happy():
    section("T1 minimal happy path")
    d = build_ctrf(
        run_record=_base_run(outcomes=[
            {"step_id": "s1", "description": "open", "ok": True, "wall_ms": 100}
        ]),
        project="demo", skill_version="1.1.0-dev",
        prompt_history=[{"timestamp": "2026-06-18T09:59:00Z", "role": "user", "content": "go"}],
    )
    ok, errs, warns = validate_ctrf(d, strict=True)
    assert ok, f"T1 expected valid, got: {errs}"
    assert d["specVersion"] == CTRF_SPEC_VERSION
    assert d["results"]["summary"]["passed"] == 1
    print("  ✓ T1")


def T2_failure_without_ai():
    section("T2 failure without ai")
    d = build_ctrf(
        run_record=_base_run(outcomes=[
            {"step_id": "s1", "description": "click", "ok": False,
             "error_msg": "selector not found"}
        ]),
        project="demo", skill_version="1.1.0-dev",
        prompt_history=[],
    )
    ok, errs, warns = validate_ctrf(d, strict=True)
    assert not ok, "T2 should fail validation"
    assert any("`ai`" in e for e in errs), f"T2 expected ai-missing error, got: {errs}"
    print("  ✓ T2")


def T3_failure_with_ai():
    section("T3 failure with ai")
    d = build_ctrf(
        run_record=_base_run(outcomes=[
            {"step_id": "s1", "description": "click", "ok": False}
        ]),
        project="demo", skill_version="1.1.0-dev",
        prompt_history=[],
        ai_diagnoses={"s1": "Selector probably changed."},
    )
    ok, errs, warns = validate_ctrf(d, strict=True)
    assert ok, f"T3 expected valid, got: {errs}"
    assert d["results"]["tests"][0]["ai"]
    print("  ✓ T3")


def T4_script_no_timestamp():
    section("T4 script without scriptGeneratedAt")
    d = build_ctrf(
        run_record=_base_run(outcomes=[
            {"step_id": "s1", "description": "open", "ok": True}
        ]),
        project="demo", skill_version="1.1.0-dev",
        prompt_history=[],
        test_scripts=[{"name": "t.py", "path": "/x/t.py", "step_id": "s1"}],
    )
    ok, errs, warns = validate_ctrf(d, strict=True)
    assert not ok and any("scriptGeneratedAt" in e for e in errs), f"got: {errs}"
    print("  ✓ T4")


def T5_script_with_timestamp():
    section("T5 script with scriptGeneratedAt")
    d = build_ctrf(
        run_record=_base_run(outcomes=[
            {"step_id": "s1", "description": "open", "ok": True}
        ]),
        project="demo", skill_version="1.1.0-dev",
        prompt_history=[],
        test_scripts=[
            {"name": "t.py", "path": "/x/t.py", "step_id": "s1",
             "generated_at": "2026-06-18T09:58:00Z"}
        ],
    )
    ok, errs, warns = validate_ctrf(d, strict=True)
    assert ok, f"got: {errs}"
    att = d["results"]["tests"][0]["attachments"][0]
    assert att["contentType"] == "text/x-python"
    assert att["extra"]["scriptGeneratedAt"] == "2026-06-18T09:58:00Z"
    print("  ✓ T5")


def T6_empty_prompt_history_ok():
    section("T6 empty promptHistory list")
    d = build_ctrf(
        run_record=_base_run(outcomes=[
            {"step_id": "s1", "description": "open", "ok": True}
        ]),
        project="demo", skill_version="1.1.0-dev",
        prompt_history=[],
    )
    ok, errs, warns = validate_ctrf(d, strict=True)
    assert ok, f"got: {errs}"
    assert d["extra"]["evoQa"]["promptHistory"] == []
    print("  ✓ T6")


def T7_missing_prompt_history_key():
    section("T7 missing promptHistory key")
    d = build_ctrf(
        run_record=_base_run(outcomes=[
            {"step_id": "s1", "description": "open", "ok": True}
        ]),
        project="demo", skill_version="1.1.0-dev",
        prompt_history=[],
    )
    del d["extra"]["evoQa"]["promptHistory"]
    ok, errs, warns = validate_ctrf(d, strict=True)
    assert not ok and any("promptHistory" in e for e in errs), f"got: {errs}"
    print("  ✓ T7")


def T8_summary_counts():
    section("T8 summary counts match tests")
    d = build_ctrf(
        run_record=_base_run(outcomes=[
            {"step_id": "s1", "ok": True},
            {"step_id": "s2", "ok": True},
            {"step_id": "s3", "ok": False},
        ]),
        project="demo", skill_version="1.1.0-dev",
        prompt_history=[],
        ai_diagnoses={"s3": "diag"},
    )
    s = d["results"]["summary"]
    assert s["tests"] == 3
    assert s["passed"] == 2
    assert s["failed"] == 1
    print("  ✓ T8")


def T9_status_enum():
    section("T9 status enum")
    d = build_ctrf(
        run_record=_base_run(outcomes=[
            {"step_id": "s1", "ok": True},
            {"step_id": "s2", "ok": False},
            {"step_id": "s3", "status": "system_failure"},  # → 'other'
        ]),
        project="demo", skill_version="1.1.0-dev",
        prompt_history=[],
        ai_diagnoses={"s2": "x"},
    )
    statuses = [t["status"] for t in d["results"]["tests"]]
    assert statuses == ["passed", "failed", "other"], statuses
    print("  ✓ T9")


def T10_write_to_disk():
    section("T10 write_ctrf_for_run produces a file")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        run_path = td / "run-X.json"
        run_path.write_text(json.dumps(_base_run(
            run_id="run-X",
            outcomes=[{"step_id": "s1", "ok": True}]
        )))
        out_dir = td / "runs" / "run-X"
        result = write_ctrf_for_run(
            run_record_path=run_path,
            out_dir=out_dir,
            project="demo",
            skill_version="1.1.0-dev",
            prompt_history=[{"timestamp": "2026-06-18T09:59:00Z",
                             "role": "user", "content": "go"}],
        )
        assert result["ok"], result["errors"]
        ctrf_path = Path(result["ctrf_path"])
        assert ctrf_path.exists()
        d = json.loads(ctrf_path.read_text())
        assert d["reportFormat"] == "CTRF"
        print(f"  ✓ T10  wrote {ctrf_path.stat().st_size} bytes")


def T11_validation_embedded():
    section("T11 validation report embedded")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        run_path = td / "r.json"
        run_path.write_text(json.dumps(_base_run(
            outcomes=[{"step_id": "s1", "ok": False}]   # failure, no ai
        )))
        # Even non-strict mode embeds validation report; in non-strict
        # mode the PQ-specific issues become warnings (writer's contract).
        result = write_ctrf_for_run(
            run_record_path=run_path,
            out_dir=td / "out",
            project="demo",
            skill_version="1.1.0-dev",
            prompt_history=[],
        )
        d = json.loads(Path(result["ctrf_path"]).read_text())
        v = d["extra"]["evoQa"]["validation"]
        # The embedded report MUST capture the issue, either as error or warning.
        all_msgs = (v.get("errors") or []) + (v.get("warnings") or [])
        assert any("ai" in m for m in all_msgs), \
            f"expected ai-missing message in embedded report, got: {all_msgs}"
        print(f"  ✓ T11  embedded {len(v['errors'])} errs, "
              f"{len(v['warnings'])} warns")


if __name__ == "__main__":
    tests = [T1_minimal_happy, T2_failure_without_ai, T3_failure_with_ai,
             T4_script_no_timestamp, T5_script_with_timestamp,
             T6_empty_prompt_history_ok, T7_missing_prompt_history_key,
             T8_summary_counts, T9_status_enum, T10_write_to_disk,
             T11_validation_embedded]
    print("=" * 60)
    print("CTRF data-layer test suite")
    print("=" * 60)
    for t in tests:
        t()
    print()
    print("=" * 60)
    print(f"All CTRF tests passed ({len(tests)}/{len(tests)}) ✅")
    print("=" * 60)
