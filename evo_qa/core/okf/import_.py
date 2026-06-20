"""
OKF import pipeline — OKF bundle directory → brain/_imported/ staging.

§20.3.B — Imports DO NOT directly merge into brain/sites/. They land in a
staging area; user/agent must promote, and promotion goes through §18.2's
4 gates (origin / confidence / observation phrasing / 2-run minimum).

Why staging:
  Trust boundary. Their brain isn't ours. We never auto-believe.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .frontmatter import Document, parse_file
from .types import RESERVED_FILENAMES


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate_bundle(bundle_root: Path) -> list[str]:
    """Lightweight OKF SPEC §9 conformance check.

    Returns a list of human-readable issues (empty list = clean bundle).
    We never raise — caller decides whether to proceed.
    """
    issues: list[str] = []
    if not bundle_root.exists():
        return [f"Bundle path does not exist: {bundle_root}"]
    if not bundle_root.is_dir():
        return [f"Bundle path is not a directory: {bundle_root}"]

    md_files = list(bundle_root.rglob("*.md"))
    if not md_files:
        issues.append("Bundle contains no .md files")
        return issues

    # Skip reserved filenames in conformance check (they have different rules).
    # README.md at bundle root is evo-qa's water-mark, not a concept.
    skip_names = set(RESERVED_FILENAMES)
    concept_files = [
        f for f in md_files
        if f.name not in skip_names
        and not (f.name == "README.md" and f.parent == bundle_root)
    ]
    if not concept_files:
        issues.append("Bundle has only reserved files (index.md / log.md), no concepts")

    for f in concept_files:
        try:
            doc = parse_file(f)
        except (OSError, ValueError):
            issues.append(f"Cannot read: {f.relative_to(bundle_root)}")
            continue
        if not doc.has_frontmatter:
            issues.append(
                f"Missing frontmatter (OKF §4.1 violation): "
                f"{f.relative_to(bundle_root)}"
            )
            continue
        if not doc.get_type():
            issues.append(
                f"Missing required `type` field (OKF §9.2 violation): "
                f"{f.relative_to(bundle_root)}"
            )

    return issues


def import_bundle(
    bundle_root,
    workspace_root,
    bundle_label: Optional[str] = None,
    strict: bool = False,
) -> dict:
    """Import bundle into workspace_root/brain/_imported/<label>/.

    Parameters
    ----------
    bundle_root : str | Path
        Source bundle directory.
    workspace_root : str | Path
        Target workspace (the project's root).
    bundle_label : str | None
        Subdirectory name under brain/_imported/. Defaults to bundle's
        directory basename + ISO date.
    strict : bool
        If True, refuse to import a non-conformant bundle. Default False
        (best-effort consumption per OKF SPEC §9).

    Returns
    -------
    dict — summary including conformance issues, files imported, etc.
    """
    bundle_root = Path(bundle_root)
    workspace_root = Path(workspace_root)

    issues = validate_bundle(bundle_root)
    if strict and issues:
        return {
            "status": "rejected_strict",
            "issues": issues,
            "imported_count": 0,
        }

    if bundle_label is None:
        bundle_label = f"{bundle_root.name}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"

    staging_root = workspace_root / "brain" / "_imported" / bundle_label
    if staging_root.exists():
        # Refuse to overwrite previous import — user can rename or delete first.
        return {
            "status": "rejected_exists",
            "staging_root": str(staging_root),
            "imported_count": 0,
        }

    staging_root.mkdir(parents=True, exist_ok=True)

    # Copy the bundle wholesale into staging — preserve directory structure.
    # We also write a sidecar `.staging.json` per concept with bridge metadata.
    from .bridge import okf_to_staging_record

    imported = 0
    skipped = 0
    records: list[dict] = []

    for f in bundle_root.rglob("*.md"):
        rel = f.relative_to(bundle_root)
        if f.name in RESERVED_FILENAMES or (
            f.name == "README.md" and f.parent == bundle_root
        ):
            # Copy verbatim — they're navigation / metadata, not concepts.
            (staging_root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, staging_root / rel)
            continue
        try:
            doc = parse_file(f)
        except (OSError, ValueError):
            skipped += 1
            continue
        if not doc.is_okf_conformant():
            skipped += 1
            # Still copy, but flag in audit.
            (staging_root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, staging_root / rel)
            continue
        # Copy + sidecar
        (staging_root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, staging_root / rel)
        sidecar = okf_to_staging_record(doc, bundle_root.name)
        sidecar_path = (staging_root / rel).with_suffix(".staging.json")
        sidecar_path.write_text(
            json.dumps(sidecar, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        records.append({"file": str(rel), **{k: sidecar[k] for k in (
            "okf_type", "incoming_confidence", "demoted_confidence", "host"
        )}})
        imported += 1

    # Bundle-level meta
    meta = {
        "imported_at": _now_iso(),
        "source_bundle": str(bundle_root),
        "source_bundle_name": bundle_root.name,
        "imported_count": imported,
        "skipped_count": skipped,
        "issues": issues,
        "records": records,
    }
    (staging_root / ".pq-import.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return {
        "status": "imported",
        "staging_root": str(staging_root),
        "imported_count": imported,
        "skipped_count": skipped,
        "issues": issues,
        "next_steps": [
            f"Review concepts under {staging_root}",
            "Run `pq brain promote --from-staging <staging_root>` to merge "
            "(applies §18.2 gates: origin / observation-phrasing / "
            "2-run minimum / confidence demotion)",
        ],
    }
