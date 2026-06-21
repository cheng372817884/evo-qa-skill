"""End-to-end test for OKF export+import.

Builds a minimal brain/system/ structure, exports to OKF bundle,
validates the bundle, then imports it back into a second workspace
and checks the staging area.
"""
from __future__ import annotations
import json
import shutil
import sys
import tempfile
import textwrap
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evo_qa.core import okf


def _build_mock_brain(workspace: Path) -> None:
    """Create a brain/system/*.yml structure that mimics a real workspace."""
    sys_dir = workspace / "brain" / "system"
    sys_dir.mkdir(parents=True)

    pages = {
        "entries": [
            {
                "name": "Quote Page",
                "url": "https://app.example.com/quote",
                "description": "PC Quote step page",
                "tags": ["quirk"],
                "notes": "Loaded by Producer pick. Contains conditional fields.",
                "known_selectors": ["#quote_form", "[name='ProducerCode']"],
                "provenance": {
                    "confidence": 0.85,
                    "evidence": ["run-2026-06-15-abc", "run-2026-06-19-def"],
                    "first_seen_run": "run-2026-06-15-abc",
                    "last_verified_run": "run-2026-06-19-def",
                    "created_at": "2026-06-15T10:00:00Z",
                    "updated_at": "2026-06-19T10:00:00Z",
                    "user_verified": False,
                },
            },
            {
                "name": "Single-run Quirk",
                "url": "https://app.example.com/single",
                "description": "Only seen once",
                "tags": ["quirk"],
                "provenance": {
                    "confidence": 0.4,
                    "evidence": ["run-2026-06-19-def"],
                    "first_seen_run": "run-2026-06-19-def",
                    "last_verified_run": "run-2026-06-19-def",
                    "created_at": "2026-06-19T10:00:00Z",
                    "updated_at": "2026-06-19T10:00:00Z",
                    "user_verified": False,
                },
            },
        ]
    }
    (sys_dir / "pages.yml").write_text(yaml.safe_dump(pages, allow_unicode=True))

    obs = {
        "entries": [
            {
                "field": "ProducerCode",
                "selector": "input[name='ProducerCode']",
                "page_id": "Quote Page",
                "required": True,
                "tags": ["selector"],
                "description": "Conditional-required field",
                "provenance": {
                    "confidence": 0.9,
                    "evidence": ["run-2026-06-15-abc", "run-2026-06-19-def"],
                    "created_at": "2026-06-15T10:00:00Z",
                    "updated_at": "2026-06-19T10:00:00Z",
                    "user_verified": True,
                },
            }
        ]
    }
    (sys_dir / "observations.yml").write_text(yaml.safe_dump(obs, allow_unicode=True))

    trans = {
        "entries": [
            {
                "from_page": "Login Page",
                "to_page": "Quote Page",
                "trigger": "click submit",
                "description": "Login → quote landing",
                "tags": ["transition"],
                "provenance": {
                    "confidence": 0.95,
                    "evidence": ["run-2026-06-15-abc", "run-2026-06-19-def"],
                    "created_at": "2026-06-15T10:00:00Z",
                    "updated_at": "2026-06-19T10:00:00Z",
                    "user_verified": False,
                },
            }
        ]
    }
    (sys_dir / "transitions.yml").write_text(yaml.safe_dump(trans, allow_unicode=True))


def _seed_with_secrets(workspace: Path) -> None:
    """Plant secrets in fields to verify redaction."""
    sys_dir = workspace / "brain" / "system"
    pages = yaml.safe_load((sys_dir / "pages.yml").read_text())
    pages["entries"][0]["notes"] = (
        "Contact: alice@acme.com. "
        "API key visible: token=sk-LIVE-1234567890abcdef. "
        "Internal ID 12345678901. "
        "AKIAIOSFODNN7EXAMPLE leaked once. "
        "JWT eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    (sys_dir / "pages.yml").write_text(yaml.safe_dump(pages, allow_unicode=True))


def main() -> int:
    print("=== OKF E2E test ===\n")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ws_a = td / "workspace_a"
        ws_b = td / "workspace_b"
        bundle = td / "bundle"

        ws_a.mkdir()
        ws_b.mkdir()

        # 1. Build mock brain in workspace A.
        _build_mock_brain(ws_a)
        _seed_with_secrets(ws_a)
        print("[1] Mock brain built in workspace A.")
        print(f"    files: {sorted(p.name for p in (ws_a / 'brain' / 'system').iterdir())}")

        # 2. Export to bundle.
        print("\n[2] Exporting workspace A → OKF bundle ...")
        audit = okf.export_to_bundle(
            workspace_root=ws_a,
            out_dir=bundle,
            include_single_run=False,
            bundle_name="acme-pc-knowledge",
        )
        summary = audit["summary"]
        print(f"    total concepts: {summary['total_concepts']}")
        print(f"    skipped low-conf: {audit['skipped_low_confidence']}")
        print(f"    redaction events: {summary['redaction_event_count']}")
        print(f"    confidence dist: {summary['confidence_distribution']}")

        assert summary["total_concepts"] == 3, \
            f"Expected 3 multi-run concepts, got {summary['total_concepts']}"
        assert audit["skipped_low_confidence"] == 1, \
            f"Expected 1 single-run skip, got {audit['skipped_low_confidence']}"
        assert summary["redaction_event_count"] >= 5, \
            f"Expected ≥5 redactions, got {summary['redaction_event_count']}"
        print("    ✅ counts match expectations")

        # 3. Validate bundle.
        print("\n[3] Validating bundle for OKF SPEC §9 conformance ...")
        issues = okf.validate_bundle(bundle)
        print(f"    issues: {issues}")
        assert issues == [], f"Bundle has issues: {issues}"
        print("    ✅ conformant")

        # 4. Verify redaction in actual file content.
        print("\n[4] Verifying redaction reached the file body ...")
        all_md = list(bundle.rglob("*.md"))
        all_text = "\n".join(p.read_text() for p in all_md)
        assert "alice@acme.com" not in all_text, "Email leaked!"
        assert "sk-LIVE-1234567890abcdef" not in all_text, "Token leaked!"
        assert "AKIAIOSFODNN7EXAMPLE" not in all_text, "AWS key leaked!"
        assert "[REDACTED_EMAIL]" in all_text or "[REDACTED]" in all_text
        print("    ✅ secrets removed, REDACTED markers present")

        # 5. Verify bundle structure.
        print("\n[5] Verifying bundle structure ...")
        assert (bundle / "README.md").exists()
        assert (bundle / "index.md").exists()
        assert (bundle / "log.md").exists()
        assert (bundle / ".pq-export-audit.json").exists()
        # okf_version must be in root index.md
        root_idx = (bundle / "index.md").read_text()
        assert 'okf_version: "0.1"' in root_idx, \
            "Root index.md missing okf_version frontmatter"
        print("    ✅ README + index.md (with okf_version) + log.md + audit present")

        # 6. Import into workspace B.
        print("\n[6] Importing bundle → workspace B ...")
        report = okf.import_bundle(
            bundle_root=bundle,
            workspace_root=ws_b,
            bundle_label="acme-import",
        )
        print(f"    status: {report['status']}")
        print(f"    imported: {report['imported_count']}")
        print(f"    issues: {report['issues']}")
        assert report["status"] == "imported"
        assert report["imported_count"] == 3
        print("    ✅ staging populated")

        # 7. Verify staging trust boundary.
        print("\n[7] Verifying staging trust boundary ...")
        staging = ws_b / "brain" / "_imported" / "acme-import"
        assert staging.exists()
        # Should NOT be in brain/system
        assert not (ws_b / "brain" / "system").exists(), \
            "Imports must not auto-merge into brain/system!"
        # Each concept has a .staging.json sidecar
        sidecars = list(staging.rglob("*.staging.json"))
        assert len(sidecars) == 3, f"Expected 3 sidecars, got {len(sidecars)}"
        # Demotion: external user-verified should now be multi-run
        meta = json.loads((staging / ".pq-import.json").read_text())
        recs = meta["records"]
        for r in recs:
            if r["incoming_confidence"] == "user-verified":
                assert r["demoted_confidence"] == "multi-run", \
                    f"user-verified must demote to multi-run, got {r}"
        print("    ✅ staging-only, sidecars present, user-verified→multi-run demotion enforced")

        # 8. Round-trip equivalence.
        print("\n[8] Re-validating staged bundle (round-trip)...")
        # Bundle was wholesale copied; should still be conformant.
        staged_issues = okf.validate_bundle(staging)
        # Allow .staging.json files to be ignored — they're sidecars.
        # validate_bundle only looks at *.md, so this is fine.
        assert staged_issues == [], f"Round-trip broken: {staged_issues}"
        print("    ✅ round-trip preserves conformance")

        print("\n=== ALL CHECKS PASSED ===")
        return 0


if __name__ == "__main__":
    sys.exit(main())
