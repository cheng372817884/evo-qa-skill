"""
Curator — periodic maintenance pass over the knowledge brain.

Responsibilities:
  1. Walk every entry under the configured knowledge directories
  2. Apply forgetting.compute_state to refresh state + weight
  3. (Optional) write the new frontmatter back to disk
  4. Compose a markdown brief summarising what changed
  5. Surface candidate promotions (project → industry — heuristic)

Curator never deletes files. Even archived entries stay on disk and
can be revived with the `revive` subcommand.

Run modes:
  - dry_run=True   (default for the `health` subcommand) — compute everything, write nothing
  - dry_run=False  (called from the `learn` subcommand) — apply state + write brief
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

import yaml

from . import forgetting as F


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class CuratorReport:
    today: str
    scanned: int = 0
    transitioned: int = 0
    by_transition: dict = field(default_factory=dict)   # 'active->stale': N
    never_archive_floored: int = 0
    top_used: list = field(default_factory=list)        # [{id,title,verified}]
    newly_stale: list = field(default_factory=list)     # [{id,title,reason}]
    newly_deprecated: list = field(default_factory=list)
    newly_archived: list = field(default_factory=list)
    promotion_candidates: list = field(default_factory=list)
    dry_run: bool = True
    brief_path: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Frontmatter I/O
# ---------------------------------------------------------------------------

_FM_RE = re.compile(r"^---\n(.*?)\n---\n?", re.S)


def _read_entry(path: Path) -> Optional[tuple[dict, str]]:
    """Return (frontmatter_dict, body_str) or None if no frontmatter."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    m = _FM_RE.match(text)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    body = text[m.end():]
    return fm, body


def _write_entry(path: Path, fm: dict, body: str) -> None:
    text = "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n" + body
    path.write_text(text, encoding="utf-8")


def _is_curatable(path: Path, root: Path) -> bool:
    """Skip indices, archives, raw imports, generated artefacts."""
    rel = path.relative_to(root)
    if path.name.startswith("_"):
        return False
    if any(part.startswith("_") for part in rel.parts):
        return False
    return path.suffix == ".md"


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def scan_entries(roots: Iterable[Path]) -> list[tuple[Path, dict, str]]:
    """Walk roots and return [(path, fm, body), ...] for curatable entries."""
    out = []
    for root in roots:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*.md")):
            if not _is_curatable(p, root):
                continue
            res = _read_entry(p)
            if res is None:
                continue
            fm, body = res
            if not fm.get("id"):
                continue
            out.append((p, fm, body))
    return out


# ---------------------------------------------------------------------------
# Promotion heuristic
# ---------------------------------------------------------------------------

def find_promotion_candidates(entries: list[tuple[Path, dict, str]]) -> list[dict]:
    """Find project-scoped entries that look like industry truths.

    Heuristic for Phase 4 (no LLM):
      - scope == 'project'
      - verified_runs >= 5
      - failed_runs / max(verified_runs,1) < 0.10
      - similar tags appear in another project too (would need cross-project
        index — for now: just propose if verified_runs is high)
    """
    out = []
    for path, fm, _body in entries:
        if (fm.get("scope") or "project") != "project":
            continue
        v = int(fm.get("verified_runs") or 0)
        f = int(fm.get("failed_runs") or 0)
        if v < 5:
            continue
        rate = F.fail_rate(v, f)
        if rate >= 0.10:
            continue
        out.append({
            "id": fm.get("id"),
            "title": fm.get("title", ""),
            "tags": fm.get("tags") or [],
            "verified_runs": v,
            "fail_rate": round(rate, 3),
            "current_path": str(path),
        })
    out.sort(key=lambda x: -x["verified_runs"])
    return out


# ---------------------------------------------------------------------------
# Main pass
# ---------------------------------------------------------------------------

def run_curator(roots: list[Path], *,
                today: Optional[date] = None,
                dry_run: bool = True,
                brief_dir: Optional[Path] = None) -> CuratorReport:
    """Apply forgetting + compose report.

    Parameters
    ----------
    roots : knowledge directories to scan
    today : override today's date (for tests)
    dry_run : if True, never writes file changes
    brief_dir : where to drop the markdown brief; None disables the brief
    """
    today = today or date.today()
    report = CuratorReport(today=today.isoformat(), dry_run=dry_run)

    entries = scan_entries(roots)
    report.scanned = len(entries)

    transitions: Counter = Counter()
    use_rank: list[tuple[int, str, str]] = []   # (verified_runs, id, title)

    for path, fm, body in entries:
        verified = int(fm.get("verified_runs") or 0)
        title = fm.get("title", fm.get("id", path.stem))
        use_rank.append((verified, fm.get("id"), title))

        verdict = F.compute_state(fm, today=today)
        prev = fm.get("review_state") or F.STATE_ACTIVE

        if verdict.transitioned:
            report.transitioned += 1
            transitions[f"{prev}->{verdict.new_state}"] += 1
            entry_summary = {
                "id": fm.get("id"),
                "title": title,
                "reason": verdict.reason,
                "path": str(path),
            }
            if verdict.new_state == F.STATE_STALE:
                report.newly_stale.append(entry_summary)
            elif verdict.new_state == F.STATE_DEPRECATED:
                report.newly_deprecated.append(entry_summary)
            elif verdict.new_state == F.STATE_ARCHIVED:
                report.newly_archived.append(entry_summary)

            if F.is_never_archive(fm) and \
               verdict.new_state == F.STATE_STALE and \
               prev == F.STATE_ACTIVE:
                # The compute already floored it; just count for visibility.
                report.never_archive_floored += 1

        if not dry_run:
            new_fm = F.apply_state(fm, verdict, today=today)
            _write_entry(path, new_fm, body)

    report.by_transition = dict(transitions)

    # Top 5 most-verified (proxy for most-used)
    use_rank.sort(reverse=True)
    report.top_used = [
        {"id": iid, "title": ttl, "verified_runs": v}
        for v, iid, ttl in use_rank[:5] if v > 0
    ]

    report.promotion_candidates = find_promotion_candidates(entries)

    # Compose brief
    if brief_dir is not None:
        brief_dir.mkdir(parents=True, exist_ok=True)
        brief_path = brief_dir / f"curator-{today.isoformat()}.md"
        brief_path.write_text(_render_brief(report), encoding="utf-8")
        report.brief_path = str(brief_path)

    return report


def _render_brief(r: CuratorReport) -> str:
    lines: list[str] = []
    lines.append(f"# Curator Brief — {r.today}")
    lines.append("")
    lines.append(f"_Mode: {'dry-run' if r.dry_run else 'applied'}_")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Entries scanned: **{r.scanned}**")
    lines.append(f"- State transitions: **{r.transitioned}**")
    if r.never_archive_floored:
        lines.append(f"- never_archive guards triggered: {r.never_archive_floored}")
    lines.append("")

    if r.by_transition:
        lines.append("### Transitions")
        lines.append("")
        for t, n in sorted(r.by_transition.items(), key=lambda x: -x[1]):
            lines.append(f"- `{t}`: {n}")
        lines.append("")

    if r.top_used:
        lines.append("## Top 5 Most-Verified Heuristics")
        lines.append("")
        lines.append("| ID | Title | Verified Runs |")
        lines.append("|---|---|---|")
        for e in r.top_used:
            lines.append(f"| `{e['id']}` | {e['title']} | {e['verified_runs']} |")
        lines.append("")

    def _section(title: str, items: list[dict]):
        if not items:
            return
        lines.append(f"## {title} ({len(items)})")
        lines.append("")
        for e in items:
            lines.append(f"- `{e['id']}` — {e['title']}")
            lines.append(f"  - reason: {e['reason']}")
        lines.append("")

    _section("Newly Stale", r.newly_stale)
    _section("Newly Deprecated", r.newly_deprecated)
    _section("Newly Archived", r.newly_archived)

    if r.promotion_candidates:
        lines.append("## Promotion Candidates (project → industry)")
        lines.append("")
        lines.append("| ID | Title | Verified | Fail Rate |")
        lines.append("|---|---|---|---|")
        for c in r.promotion_candidates:
            lines.append(f"| `{c['id']}` | {c['title']} | {c['verified_runs']} | {c['fail_rate']:.1%} |")
        lines.append("")

    if not (r.transitioned or r.promotion_candidates):
        lines.append("_The brain is healthy — no action needed._")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# the `revive` subcommand helper — single-entry override
# ---------------------------------------------------------------------------

def revive_entry(knowledge_id: str, roots: list[Path], *,
                 by: str = "manual revive",
                 note: str = "",
                 today: Optional[date] = None,
                 dry_run: bool = False) -> dict:
    """Locate entry by id across roots, lift state, log revival event."""
    today = today or date.today()
    for path, fm, body in scan_entries(roots):
        if fm.get("id") == knowledge_id:
            new_fm = F.revive(fm, by=by, note=note, today=today)
            if not dry_run:
                _write_entry(path, new_fm, body)
            return {
                "ok": True,
                "id": knowledge_id,
                "from_state": fm.get("review_state") or F.STATE_ACTIVE,
                "to_state": new_fm["review_state"],
                "path": str(path),
                "dry_run": dry_run,
            }
    return {"ok": False, "id": knowledge_id, "msg": "not found in any root"}


__all__ = [
    "CuratorReport", "run_curator", "revive_entry", "scan_entries",
    "find_promotion_candidates",
]
