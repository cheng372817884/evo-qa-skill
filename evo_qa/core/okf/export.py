"""
OKF export pipeline — brain → OKF bundle directory.

Order of operations (REQUIREMENTS-v1.4.md §20.3.A):

  1. Discover candidate concepts in brain/
  2. Apply Gate 1 confidence filter (single-run dropped unless --include-single-run)
  3. Convert each to OKF Document via bridge.py
  4. Apply redaction pipeline to every Document (mandatory)
  5. Write to bundle directory under conventional path
  6. Generate per-directory index.md
  7. Generate bundle root index.md (with okf_version)
  8. Generate log.md from updated_at timestamps
  9. Generate bundle README with audit metadata

The output directory is the user-supplied path. We never auto-upload.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import bundle as B
from . import bridge
from .frontmatter import Document, write_file as write_doc
from .redact import redact_document, load_custom_rules, RedactionEvent
from .types import EXPORTABLE_CONFIDENCE


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Discovery — how we find concepts in a workspace.

def discover_concepts(workspace_root: Path) -> list[tuple[str, dict, str]]:
    """Walk brain/system/*.yml and emit (kind, raw_record, host) tuples.

    `kind` is one of "page", "field_observation", "transition" — picked up
    by the dispatcher in `_record_to_doc`.

    `host` is best-effort extracted from the record's `url` or `page_id`.
    Empty string if unknown — those concepts go to `_unknown/` in the bundle.
    """
    import yaml
    from urllib.parse import urlparse

    sys_dir = Path(workspace_root) / "brain" / "system"
    if not sys_dir.exists():
        return []

    out: list[tuple[str, dict, str]] = []

    file_to_kind = {
        "pages.yml": "page",
        "transitions.yml": "transition",
        "observations.yml": "field_observation",
    }

    for fname, kind in file_to_kind.items():
        f = sys_dir / fname
        if not f.exists():
            continue
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        # Storage uses a top-level `entries:` list (see system_brain/storage.py).
        entries = data.get("entries") if isinstance(data, dict) else data
        if not isinstance(entries, list):
            continue
        for record in entries:
            if not isinstance(record, dict):
                continue
            host = ""
            url = record.get("url") or record.get("resource") or ""
            if url:
                try:
                    host = urlparse(url).hostname or ""
                except Exception:
                    host = ""
            if not host:
                host = record.get("host") or ""
            out.append((kind, record, host))

    return out


def _record_to_doc(kind: str, record: dict, host: str) -> Optional[Document]:
    """Dispatch a discovered record to the right bridge function."""
    if kind == "page":
        return bridge.page_node_to_okf(record, host)
    if kind == "field_observation":
        return bridge.field_observation_to_okf(record, host)
    if kind == "transition":
        return bridge.transition_to_okf(record, host)
    return None


# ---------------------------------------------------------------------------
# Filter

def _passes_confidence_gate(doc: Document, include_single_run: bool) -> bool:
    """§18.2 Gate 1 — only multi-run / user-verified by default."""
    c = doc.frontmatter.get("pq_confidence", "single-run") if doc.frontmatter else "single-run"
    if include_single_run:
        return True
    return c in EXPORTABLE_CONFIDENCE


# ---------------------------------------------------------------------------
# Public API

def export_to_bundle(
    workspace_root,
    out_dir,
    include_single_run: bool = False,
    bundle_name: Optional[str] = None,
    pq_version: str = "1.4.0",
) -> dict:
    """Top-level export. Returns a summary dict suitable for JSON output.

    Parameters
    ----------
    workspace_root : str | Path
        Path containing `brain/system/*.yml`.
    out_dir : str | Path
        Destination directory. Will be created. Must NOT exist yet OR be
        empty — we refuse to overwrite an arbitrary directory.
    include_single_run : bool
        If True, single-run observations are exported with a warning marker.
        Not recommended — defaults to False.
    bundle_name : str | None
        Display name for the bundle README. Defaults to out_dir's basename.
    pq_version : str
        evo-qa version string (recorded in README).
    """
    workspace_root = Path(workspace_root)
    out_dir = Path(out_dir)

    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(
            f"Refusing to export into non-empty directory: {out_dir}. "
            f"Pick a fresh path."
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    bundle_name = bundle_name or out_dir.name

    custom_rules = load_custom_rules(workspace_root)

    # 1+2. Discover & convert
    discovered = discover_concepts(workspace_root)
    docs: list[tuple[Document, Path]] = []  # (doc, target_relpath)
    skipped_low_confidence = 0

    for kind, record, host in discovered:
        doc = _record_to_doc(kind, record, host)
        if doc is None:
            continue
        if not _passes_confidence_gate(doc, include_single_run):
            skipped_low_confidence += 1
            continue
        # Compute target path
        okf_type = doc.frontmatter.get("type", "Reference")
        title = doc.frontmatter.get("title") or "concept"
        slug = B.slugify(title)
        rel_path = B.concept_path(host, okf_type, slug)
        docs.append((doc, rel_path))

    # 3. Redact every document
    redaction_events: list[RedactionEvent] = []
    redacted_docs: list[tuple[Document, Path]] = []
    for doc, rel in docs:
        new_doc, events = redact_document(doc, custom_rules)
        redaction_events.extend(events)
        redacted_docs.append((new_doc, rel))

    # 4. Write each document
    for doc, rel in redacted_docs:
        target = out_dir / rel
        write_doc(target, doc)

    # 5. Generate per-directory index.md
    by_dir: dict[Path, list[tuple[str, str, str]]] = defaultdict(list)
    for doc, rel in redacted_docs:
        parent = (out_dir / rel).parent.relative_to(out_dir)
        title = doc.frontmatter.get("title") or rel.stem
        desc = doc.frontmatter.get("description") or ""
        # url relative to the directory housing the index
        url = rel.name
        by_dir[parent].append((url, title, desc))

    # Also populate parent-of-parent directories with subdirectory listings.
    # Simple approach: for each directory with concepts, walk up and emit
    # an index that lists immediate children directories + concepts.
    all_dirs: set[Path] = set()
    for d in by_dir:
        all_dirs.add(d)
        for parent in d.parents:
            all_dirs.add(parent)

    for d in all_dirs:
        # Direct children (concepts in d) + immediate subdirs
        entries: list[tuple[str, str, str]] = []
        # subdirs
        sub_dirs = {sd for sd in all_dirs if sd != d and sd.parent == d}
        for sd in sorted(sub_dirs):
            entries.append((f"{sd.name}/", sd.name, "subdirectory"))
        # leaf concepts
        for url, title, desc in sorted(by_dir.get(d, [])):
            entries.append((url, title, desc))
        is_root = (d == Path("."))
        B.write_index(out_dir / d, entries, bundle_root=is_root)

    # 6. log.md from timestamps
    log_events: list[tuple[str, str]] = []
    for doc, rel in redacted_docs:
        ts = doc.frontmatter.get("timestamp") or _now_iso()
        date = ts.split("T", 1)[0] if "T" in ts else ts[:10]
        title = doc.frontmatter.get("title") or rel.stem
        log_events.append((date, f"**Initialization**: [{title}]({rel.as_posix()})"))
    (out_dir / "log.md").write_text(B.render_log(log_events), encoding="utf-8")

    # 7. Bundle README
    meta = {
        "name": bundle_name,
        "pq_version": pq_version,
        "generated_at": _now_iso(),
        "source_workspace_hash": B.workspace_fingerprint(workspace_root),
        "okf_version": "0.1",
        "redaction_applied": True,
        "redaction_event_count": len(redaction_events),
        "total_concepts": len(redacted_docs),
        "confidence_distribution": B.confidence_distribution(d for d, _ in redacted_docs),
    }
    B.write_bundle_readme(out_dir, meta)

    # 8. Audit log (machine-readable)
    audit = {
        "summary": meta,
        "skipped_low_confidence": skipped_low_confidence,
        "redactions": [
            {
                "pattern": ev.pattern,
                "replacement": ev.replacement,
                "location_hint": ev.location_hint,
            }
            for ev in redaction_events
        ],
    }
    import json
    (out_dir / ".pq-export-audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return audit
