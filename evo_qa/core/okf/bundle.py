"""
OKF bundle layout, index.md / log.md generation, and water-marking.

A bundle is a directory tree (REQUIREMENTS-v1.4.md §20.2.A; OKF SPEC §3):

    bundle_root/
    ├── README.md           # evo-qa-specific water-mark (not in OKF)
    ├── index.md            # OKF SPEC §6 — directory listing
    ├── log.md              # OKF SPEC §7 — chronological history
    └── sites/<host>/
        ├── index.md
        ├── quirks/<concept>.md
        ├── selectors/<concept>.md
        └── flows/<concept>.md

We always emit `okf_version` in the root index.md frontmatter — OKF SPEC §11
declares this is the only place frontmatter is permitted in an index.md.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .frontmatter import Document, write_file
from .types import OKF_VERSION, BUNDLE_README_KEYS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Concept paths

def concept_path(host: str, okf_type: str, slug: str) -> Path:
    """Where in the bundle a concept of given type lives.

    Layout:
      sites/<host>/quirks/<slug>.md
      sites/<host>/selectors/<slug>.md
      sites/<host>/flows/<slug>.md
      sites/<host>/api-contracts/<slug>.md
      heuristics/<slug>.md          (cross-site)
      playbooks/<slug>.md           (cross-site)
    """
    type_to_dir = {
        "Quirk": "quirks",
        "Selector": "selectors",
        "Flow": "flows",
        "ApiContract": "api-contracts",
        "DeprecatedSelector": "deprecated",
        "RecurringIssue": "recurring-issues",
        "Heuristic": None,    # cross-site
        "Playbook": None,
        "Reference": None,
    }
    bucket = type_to_dir.get(okf_type, "concepts")

    if bucket is None:
        # Cross-site concept lives at bundle root.
        return Path(_kind_to_root_dir(okf_type)) / f"{slug}.md"

    if not host:
        host = "_unknown"
    return Path("sites") / host / bucket / f"{slug}.md"


def _kind_to_root_dir(okf_type: str) -> str:
    return {
        "Heuristic": "heuristics",
        "Playbook": "playbooks",
        "Reference": "references",
    }.get(okf_type, "concepts")


def slugify(text: str) -> str:
    """Lowercase + dash + safe-only characters. Stable for similar inputs."""
    import re
    s = (text or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        # Hash-derived fallback so we never produce empty filenames.
        s = "concept-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return s[:80]


# ---------------------------------------------------------------------------
# index.md generation (OKF SPEC §6)

def render_index(directory: Path, entries: list[tuple[str, str, str]],
                 bundle_root: bool = False) -> str:
    """Render an index.md body.

    Parameters
    ----------
    directory : Path
        The directory this index describes (relative to bundle root).
    entries : list of (relative_url, title, description)
    bundle_root : bool
        If True, emit `okf_version` frontmatter (only allowed at root —
        OKF SPEC §11).
    """
    lines: list[str] = []

    if bundle_root:
        lines.append("---")
        lines.append(f'okf_version: "{OKF_VERSION}"')
        lines.append("---")
        lines.append("")

    lines.append(f"# {directory.name or 'Bundle Index'}")
    lines.append("")

    # Group by parent path (one level down) for readability.
    if not entries:
        lines.append("_(empty)_")
        return "\n".join(lines) + "\n"

    by_parent: dict[str, list[tuple[str, str, str]]] = {}
    for rel_url, title, desc in entries:
        # Section heading = first path segment, "Documents" if flat.
        parts = rel_url.split("/", 1)
        section = parts[0] if len(parts) > 1 else "Documents"
        by_parent.setdefault(section, []).append((rel_url, title, desc))

    for section in sorted(by_parent):
        lines.append(f"## {section}")
        lines.append("")
        for rel_url, title, desc in sorted(by_parent[section]):
            entry = f"* [{title}]({rel_url})"
            if desc:
                entry += f" — {desc}"
            lines.append(entry)
        lines.append("")

    return "\n".join(lines)


def write_index(directory: Path, entries, bundle_root: bool = False) -> None:
    body = render_index(directory, list(entries), bundle_root=bundle_root)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.md").write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# log.md generation (OKF SPEC §7)

def render_log(events: list[tuple[str, str]]) -> str:
    """events: list of (date_iso_yyyy_mm_dd, prose_line). Newest first."""
    if not events:
        return "# Bundle Update Log\n\n_(none recorded)_\n"
    by_date: dict[str, list[str]] = {}
    for date, line in events:
        by_date.setdefault(date, []).append(line)

    lines = ["# Bundle Update Log", ""]
    for date in sorted(by_date.keys(), reverse=True):
        lines.append(f"## {date}")
        for entry in by_date[date]:
            lines.append(f"* {entry}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Bundle README water-mark (REQUIREMENTS-v1.4.md §20.3.D)

def render_bundle_readme(meta: dict) -> str:
    """Render the evo-qa-specific README at bundle root.

    This file is NOT part of OKF SPEC — OKF only requires markdown +
    frontmatter. This is our audit artifact.
    """
    lines = [
        f"# OKF Bundle: {meta.get('name', 'unnamed')}",
        "",
        "> This bundle was generated by **evo-qa**. Each concept",
        "> document conforms to the [Open Knowledge Format (OKF) v0.1]"
        "(https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md).",
        "",
        "## Provenance",
        "",
        f"- **Generated by**: evo-qa v{meta.get('pq_version', '?')}",
        f"- **Generated at**: {meta.get('generated_at', _now_iso())}",
        f"- **Source workspace**: `{meta.get('source_workspace_hash', 'unknown')}` (sha1, last 12 chars)",
        f"- **OKF version**: {meta.get('okf_version', OKF_VERSION)}",
        f"- **Redaction applied**: {'yes' if meta.get('redaction_applied') else 'no'}",
        f"- **Redaction events**: {meta.get('redaction_event_count', 0)}",
        "",
        "## Contents",
        "",
        f"- **Total concepts**: {meta.get('total_concepts', 0)}",
        "- **Confidence distribution**:",
    ]
    dist = meta.get("confidence_distribution", {}) or {}
    for k in ("user-verified", "multi-run"):
        lines.append(f"  - `{k}`: {dist.get(k, 0)}")
    if dist.get("single-run"):
        lines.append(
            f"  - `single-run`: {dist['single-run']} "
            "(filtered out — should be 0 in shipped bundles)"
        )

    lines.extend([
        "",
        "## How to consume",
        "",
        "Any markdown reader (Obsidian, Notion, MkDocs, Hugo, plain `cat`) "
        "can browse this bundle. For graph-shaped exploration, the upstream "
        "OKF reference repo provides a Cytoscape-based viewer:",
        "",
        "    https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf",
        "",
        "## Caveats",
        "",
        "- OKF v0.1 is a **draft** specification. Forward compatibility is",
        "  best-effort. evo-qa's importer will degrade gracefully on",
        "  unknown OKF versions.",
        "- Redaction is **heuristic**, not deterministic. Review the bundle",
        "  before sharing externally.",
        "- External `pq_confidence: user-verified` is auto-demoted to",
        "  `multi-run` on import. Their user-verified is not ours.",
        "",
        "## License",
        "",
        "Concept content originates from the source workspace. The OKF format "
        "itself is published under Apache 2.0 by GoogleCloudPlatform/"
        "knowledge-catalog (★[P6]).",
        "",
    ])
    return "\n".join(lines)


def write_bundle_readme(bundle_root: Path, meta: dict) -> None:
    bundle_root.mkdir(parents=True, exist_ok=True)
    (bundle_root / "README.md").write_text(
        render_bundle_readme(meta), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Workspace fingerprint (one-way hash, no PII)

def workspace_fingerprint(workspace_root: Path) -> str:
    """A short, deterministic, non-reversible identifier for the workspace.

    Used in bundle README to indicate origin without leaking the path.
    """
    return hashlib.sha1(
        str(Path(workspace_root).resolve()).encode("utf-8")
    ).hexdigest()[-12:]


# ---------------------------------------------------------------------------
# Confidence distribution helper

def confidence_distribution(docs: Iterable[Document]) -> dict[str, int]:
    counts = Counter()
    for d in docs:
        c = d.frontmatter.get("pq_confidence", "single-run") if d.frontmatter else "single-run"
        counts[c] += 1
    return dict(counts)
