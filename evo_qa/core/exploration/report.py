"""
Render an ExplorationReport to disk.

Output format: YAML front-matter + Markdown body. Same shape the rest
of the brain uses (so retriever finds it, curator can age it).

Persisted at:  <workspace>/brain/exploration/<report.id>.md

We deliberately keep this dumb. No templating engine — just string
concatenation. The exploration report is meant to be read by humans
and by the next call's MemoryGate.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .schemas import ExplorationReport, ExplorationStep
from .._atomic import atomic_write


def render(report: ExplorationReport) -> str:
    fm = {
        "id": report.id,
        "kind": "exploration",
        "charter_kind": report.charter.kind,
        "charter_raw": report.charter.raw,
        "target_url": report.charter.target_url,
        "project": report.charter.project,
        "started_at": report.started_at,
        "ended_at": report.ended_at,
        "status": report.status,
        "step_count": len(report.steps),
        "pages_discovered": report.pages_discovered,
        "selectors_added": report.selectors_added,
        "review_state": "active",
    }
    front = "---\n" + yaml.safe_dump(fm, sort_keys=False,
                                     allow_unicode=True) + "---\n\n"

    body = []
    body.append(f"# Exploration: {report.charter.raw}\n")
    body.append(f"**Charter kind:** `{report.charter.kind}`  "
                f"**Status:** `{report.status}`  "
                f"**Steps:** {len(report.steps)}\n")
    if report.error:
        body.append(f"\n**Error:** {report.error}\n")

    body.append("\n## Steps\n")
    for s in report.steps:
        body.append(_render_step(s))

    if report.pages_discovered:
        body.append("\n## Pages discovered\n")
        for p in report.pages_discovered:
            body.append(f"- {p}\n")

    if report.selectors_added:
        body.append("\n## Selectors captured\n")
        for sel in report.selectors_added[:50]:  # cap
            body.append(f"- `{sel}`\n")
        if len(report.selectors_added) > 50:
            body.append(f"- … and {len(report.selectors_added) - 50} more\n")

    if report.business_signals:
        body.append("\n## Business signals\n")
        for sig in report.business_signals:
            body.append(f"- {sig}\n")

    if report.known_unknowns:
        body.append("\n## Known unknowns\n")
        for u in report.known_unknowns:
            body.append(f"- {u}\n")

    return front + "".join(body)


def _render_step(step: ExplorationStep) -> str:
    a = step.action
    skipped = " · *skipped*" if a.skipped else ""
    line = (f"\n### Step {step.index + 1}: {a.kind}"
            f" → `{a.target_ref or a.value or ''}`{skipped}\n")
    if a.rationale:
        line += f"- _why:_ {a.rationale}\n"
    if a.skipped_reason:
        line += f"- _skipped:_ {a.skipped_reason}\n"
    if a.expected:
        line += f"- _expected:_ {a.expected}\n"
    o = step.outcome
    if o.error:
        line += f"- _error:_ {o.error}\n"
    if o.new_url:
        line += f"- _new url:_ `{o.new_url}`\n"
    if o.title_changed:
        line += f"- _title changed_\n"
    if o.new_elements_count:
        line += f"- _new elements:_ {o.new_elements_count}\n"
    if step.notes:
        line += f"- _notes:_ {', '.join(step.notes)}\n"
    return line


def write(report: ExplorationReport, brain_dir: Path) -> Path:
    out_dir = Path(brain_dir) / "exploration"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{report.id}.md"
    atomic_write(out, render(report))
    return out


__all__ = ["render", "write"]
