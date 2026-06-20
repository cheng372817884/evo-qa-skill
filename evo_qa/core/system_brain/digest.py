"""
Render a markdown digest of the system brain — human-readable, honest.

The header has a permanent disclaimer reminding the reader that this is
OBSERVATIONS, not LAWS. Every section shows confidence + evidence count.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .storage import SystemBrain


HEADER_DISCLAIMER = """\
> **⚠️ This is observation, not law.**
> Each entry below is something Evo QA has *seen happen* during
> recorded runs. It is **NOT** a guaranteed property of the system.
> Always read the `known_unknowns` and `evidence` of any entry before
> relying on it. Real systems change; this brain is conservative
> on purpose.
"""


def _state_badge(state: str) -> str:
    return {
        "active":     "🟢 active",
        "stale":      "🟡 stale",
        "deprecated": "🔴 deprecated",
        "archived":   "⚪ archived",
    }.get(state, state)


def _conf_bar(c: float) -> str:
    n = int(round(c * 10))
    return "█" * n + "░" * (10 - n) + f" {c:.2f}"


def render_digest(brain: SystemBrain, *, project: str) -> str:
    s = brain.stats()
    out: list[str] = []

    out.append(f"# System Brain — {project}")
    out.append("")
    out.append(HEADER_DISCLAIMER)
    out.append("")
    out.append(f"_Generated: {datetime.utcnow().isoformat(timespec='seconds')}Z_")
    out.append("")

    # Stats overview
    out.append("## Overview")
    out.append("")
    out.append("| Layer | Total | Active | Stale | Deprecated |")
    out.append("|---|---:|---:|---:|---:|")
    for k in ("pages", "transitions", "observations"):
        d = s[k]
        out.append(
            f"| {k} | {d['total']} | {d['active']} | {d['stale']} | "
            f"{d['deprecated']} |"
        )
    out.append("")
    out.append(f"**Open questions:** {s['questions']['open']}  ·  "
               f"**Answered:** {s['questions']['answered']}  ·  "
               f"**Unresolved contradictions:** "
               f"{s['contradictions']['unresolved']}")
    out.append("")

    # Pages
    if brain.pages:
        out.append("## L1 — Pages observed")
        out.append("")
        for p in sorted(brain.pages.values(), key=lambda x: x.id):
            out.append(f"### `{p.id}` — {p.title_pattern}")
            out.append(f"- State: {_state_badge(p.prov.review_state)}")
            out.append(f"- Confidence: `{_conf_bar(p.prov.confidence)}`")
            out.append(f"- Evidence: {len(p.prov.evidence)} run(s) — "
                       f"`{', '.join(p.prov.evidence[:3])}`"
                       + (" ..." if len(p.prov.evidence) > 3 else ""))
            if p.title_aliases:
                out.append(f"- Title aliases (revisions): "
                           f"{', '.join(p.title_aliases)}")
            if p.prov.last_verified_build:
                out.append(f"- Last seen build: `{p.prov.last_verified_build}`")
            out.append("")

    # Transitions
    if brain.transitions:
        out.append("## L2 — Transitions (page edges)")
        out.append("")
        for t in sorted(brain.transitions.values(), key=lambda x: x.id):
            out.append(f"### `{t.from_page}` → `{t.to_page}`")
            out.append(f"- Intent: {t.intent}")
            out.append(f"- State: {_state_badge(t.prov.review_state)}  ·  "
                       f"Conf: `{_conf_bar(t.prov.confidence)}`  ·  "
                       f"Evidence: {len(t.prov.evidence)} run(s)")
            if t.trigger_atoms:
                triggers = "; ".join(
                    f"{a.get('atom')}({a.get('target','')[:40]})"
                    for a in t.trigger_atoms[:3]
                )
                out.append(f"- Triggers: {triggers}")
            out.append("")

    # Field observations
    if brain.observations:
        out.append("## L3 — Field observations")
        out.append("")
        out.append("> Values seen are values that have been entered AND "
                   "accepted. Not a constraint — just a record.")
        out.append("")
        # Group by page
        by_page: dict[str, list] = {}
        for o in brain.observations.values():
            by_page.setdefault(o.page, []).append(o)
        for page in sorted(by_page):
            out.append(f"### Page `{page}`")
            out.append("")
            for o in sorted(by_page[page], key=lambda x: x.id):
                out.append(f"#### `{o.id}`")
                out.append(f"- Selector: `{o.selector}`")
                out.append(f"- Kind: {o.field_kind}  ·  "
                           f"Operations: {', '.join(o.operations_seen)}")
                if o.values_seen:
                    vs = o.values_seen[:5]
                    more = "" if len(o.values_seen) <= 5 \
                        else f" (+{len(o.values_seen)-5} more)"
                    out.append(f"- Values seen: "
                               + ", ".join(f"`{v}`" for v in vs)
                               + more)
                if o.quirks:
                    out.append(f"- Quirks: {', '.join(o.quirks)}")
                out.append(f"- State: {_state_badge(o.prov.review_state)}  ·  "
                           f"Conf: `{_conf_bar(o.prov.confidence)}`  ·  "
                           f"Evidence: {len(o.prov.evidence)} run(s)")
                out.append("")

    # Questions — these are explicit known unknowns, the heart of "honesty"
    if brain.questions:
        out.append("## L4 — Open questions (known unknowns)")
        out.append("")
        out.append("> These drive future exploration. An answer becomes a new "
                   "observation; the question is archived (not deleted).")
        out.append("")
        for q in sorted(brain.questions.values(), key=lambda x: x.id):
            badge = {"open": "❓", "answered": "✅",
                     "obsolete": "⚪"}[q.state]
            out.append(f"### {badge} `{q.id}`")
            out.append(f"- {q.text}")
            if q.suggested_test:
                out.append(f"- *Suggested test:* {q.suggested_test}")
            if q.related_entries:
                out.append(f"- Related: "
                           + ", ".join(f"`{r}`" for r in q.related_entries[:5]))
            if q.state == "answered":
                out.append(f"- **Answer:** {q.answer}  "
                           f"(by run `{q.answered_by_run}`)")
            out.append("")

    # Contradictions — separate section so they're not buried
    if brain.contradictions:
        out.append("## L5 — Contradictions (recorded, not silently overwritten)")
        out.append("")
        for c in sorted(brain.contradictions.values(), key=lambda x: x.id):
            res = "✅ resolved" if c.resolved else "⚠️ unresolved"
            out.append(f"### `{c.id}` — {res}")
            out.append(f"- Severity: {c.severity}")
            out.append(f"- Affects: `{c.affected_entry}`")
            out.append(f"- Detected at: {c.detected_at}  "
                       f"(run `{c.run_id}`)")
            out.append(f"- Expected: {c.expected}")
            out.append(f"- Observed: {c.observed}")
            if c.spawned_question:
                out.append(f"- Spawned question: `{c.spawned_question}`")
            if c.resolution:
                out.append(f"- Resolution: {c.resolution}")
            out.append("")

    out.append("---")
    out.append("")
    out.append("_Brain is conservative on purpose. If you expected to see "
               "more here, run more cases — that's how it grows._")

    return "\n".join(out)


def write_digest(brain: SystemBrain, *, project: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_digest(brain, project=project), encoding="utf-8")
    return out_path


__all__ = ["render_digest", "write_digest"]
