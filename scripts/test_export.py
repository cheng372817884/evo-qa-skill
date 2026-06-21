"""Test portable export (mem0 / ctrf / json)."""
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from evo_qa.core.workspace import Workspace
from evo_qa.core.schemas import WorkspaceConfig
from evo_qa.core.reporting import portable_export
from evo_qa.core.reporting import write_ctrf_for_run


def _setup_workspace(tmp: Path) -> Workspace:
    """Create a real workspace with one change + one run with CTRF."""
    ws = Workspace("demo", root=tmp)
    cfg = WorkspaceConfig(name="demo", url="https://example.test")
    ws.init(cfg)
    # Inject one change manually
    cid = "test-login"
    cdir = ws.get_change_dir(cid)
    cdir.mkdir(parents=True, exist_ok=True)
    runs_dir = cdir / "runs"
    runs_dir.mkdir(exist_ok=True)
    run = {
        "id": "run-1", "change_id": cid,
        "started_at": "2026-06-18T10:00:00Z",
        "ended_at": "2026-06-18T10:01:00Z",
        "verdict": "pass",
        "outcomes": [{"step_id": "s1", "ok": True}],
    }
    rp = runs_dir / "run-1.json"
    rp.write_text(json.dumps(run))
    write_ctrf_for_run(
        run_record_path=rp,
        out_dir=runs_dir / "run-1",
        project="demo", skill_version="1.1.0-test",
        prompt_history=[{"timestamp": "T", "role": "user", "content": "go"}],
    )
    # Inject a brain page so mem0 export has something to chew on
    sys_dir = ws.brain_dir / "system"
    sys_dir.mkdir(parents=True, exist_ok=True)
    (sys_dir / "pages.yml").write_text(
        "- id: page-1\n  title: Login\n  url: https://x/login\n  state: active\n"
        "- id: page-2\n  title: Dashboard\n  url: https://x/dash\n  state: active\n"
    )
    (sys_dir / "observations.yml").write_text(
        "- id: obs-1\n  claim: Login button is orange\n  state: active\n"
    )
    return ws


def section(name): print(f"\n--- {name} ---")


def E1_ctrf_bundle():
    section("E1 ctrf bundle")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ws = _setup_workspace(td)
        result = portable_export.export(workspace=ws, fmt="ctrf")
        assert result["ok"], result
        assert result["count"] == 1
        idx = json.loads((Path(result["out_dir"]) / "index.json").read_text())
        assert idx["count"] == 1
        assert idx["items"][0]["change_id"] == "test-login"
        print(f"  ✓ E1  bundled {result['count']} CTRF doc(s)")


def E2_mem0_export():
    section("E2 mem0 export")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ws = _setup_workspace(td)
        result = portable_export.export(workspace=ws, fmt="mem0")
        assert result["ok"], result
        assert result["count"] == 3, f"expected 3 entries, got {result['count']}"
        memories = json.loads(Path(result["out_file"]).read_text())
        assert len(memories) == 3
        # mem0 contract: each entry has 'memory', 'metadata'
        for m in memories:
            assert "memory" in m
            assert "metadata" in m
            assert m["metadata"]["skill"] == "evo-qa"
            assert m["agent_id"] == "evo-qa"
        # README explains how to import
        readme = Path(result["out_dir"]) / "README.md"
        assert readme.exists()
        assert "mem0 import" in readme.read_text()
        print(f"  ✓ E2  exported {len(memories)} mem0-compatible memories")


def E3_raw_json():
    section("E3 raw json dump")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ws = _setup_workspace(td)
        result = portable_export.export(workspace=ws, fmt="json")
        assert result["ok"], result
        bundle = json.loads(Path(result["out_file"]).read_text())
        assert "files" in bundle
        assert "system/pages.yml" in bundle["files"]
        assert len(bundle["files"]["system/pages.yml"]) == 2
        print(f"  ✓ E3  dumped {len(bundle['files'])} brain file(s)")


def E4_unknown_format():
    section("E4 unknown format → ok=False")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ws = _setup_workspace(td)
        result = portable_export.export(workspace=ws, fmt="garbage")
        assert result["ok"] is False
        assert "Unknown format" in result["msg"]
        print("  ✓ E4")


if __name__ == "__main__":
    tests = [E1_ctrf_bundle, E2_mem0_export, E3_raw_json, E4_unknown_format]
    print("=" * 60)
    print("Portable export test suite")
    print("=" * 60)
    for t in tests:
        t()
    print()
    print("=" * 60)
    print(f"All export tests passed ({len(tests)}/{len(tests)}) ✅")
    print("=" * 60)
