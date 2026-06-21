"""Portable brain/run export.

Three formats:

- `mem0`: one JSON document, an array of memory entries compatible
  with `mem0 import`. Each entry: {memory, user_id, agent_id,
  metadata, created_at}.
- `ctrf`: a directory of `result.ctrf.json` files (one per run),
  optionally with an index.
- `json`: raw brain dump: pages, transitions, observations, plus
  any indices we maintain.

Stage 6 fills these in. This stub keeps the CLI honest while CTRF
and BM25 work happens; calling export today returns a clear "not
yet implemented" with format-specific guidance.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def export(*, workspace, fmt: str, out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Dispatch by format."""
    out_dir = Path(out_dir) if out_dir else (workspace.root / "exports" / fmt)
    out_dir.mkdir(parents=True, exist_ok=True)

    if fmt == "ctrf":
        return _export_ctrf_bundle(workspace, out_dir)
    if fmt == "mem0":
        return _export_mem0(workspace, out_dir)
    if fmt == "json":
        return _export_raw_json(workspace, out_dir)
    return {"ok": False, "msg": f"Unknown format: {fmt}"}


def _export_ctrf_bundle(workspace, out_dir: Path) -> Dict[str, Any]:
    """Walk every change and copy the latest result.ctrf.json into the bundle."""
    bundle = []
    copied = 0
    for cid in workspace.list_changes():
        change_dir = workspace.get_change_dir(cid)
        runs_dir = change_dir / "runs"
        if not runs_dir.exists():
            continue
        for run_subdir in runs_dir.iterdir():
            if not run_subdir.is_dir():
                continue
            ctrf = run_subdir / "result.ctrf.json"
            if not ctrf.exists():
                continue
            try:
                doc = json.loads(ctrf.read_text())
            except Exception:
                continue
            target = out_dir / cid / f"{run_subdir.name}.ctrf.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
            bundle.append({
                "change_id": cid,
                "run_id": run_subdir.name,
                "path": str(target.relative_to(out_dir)),
                "summary": doc.get("results", {}).get("summary", {}),
            })
            copied += 1
    index = {
        "exportedAt": _utcnow_iso(),
        "format": "ctrf-bundle-v1",
        "project": workspace.project,
        "count": copied,
        "items": bundle,
    }
    (out_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False))
    return {"ok": True, "format": "ctrf", "out_dir": str(out_dir),
            "count": copied}


def _export_mem0(workspace, out_dir: Path) -> Dict[str, Any]:
    """Minimal mem0-compatible export.

    mem0 import accepts a JSON array of objects with at least:
        {"memory": str, "metadata": {...}}
    plus optional user_id / agent_id / run_id / created_at.

    We translate brain entries (pages, observations, contradictions)
    into one memory each. Provenance is preserved in metadata so a
    future re-import can round-trip.
    """
    import yaml  # PyYAML is already a transitive dep of the brain
    entries: List[Dict[str, Any]] = []

    brain_dir = workspace.brain_dir / "system"
    sources = [
        ("page", brain_dir / "pages.yml"),
        ("transition", brain_dir / "transitions.yml"),
        ("observation", brain_dir / "observations.yml"),
        ("question", brain_dir / "questions.yml"),
        ("contradiction", brain_dir / "contradictions.yml"),
    ]
    for kind, path in sources:
        if not path.exists():
            continue
        try:
            data = yaml.safe_load(path.read_text()) or []
        except Exception:
            continue
        if isinstance(data, dict):
            data = list(data.values())
        for item in data:
            if not isinstance(item, dict):
                continue
            mem_text = _summarize_for_mem0(kind, item)
            if not mem_text:
                continue
            entries.append({
                "memory": mem_text,
                "agent_id": "evo-qa",
                "user_id": workspace.project,
                "metadata": {
                    "kind": kind,
                    "source_id": item.get("id", ""),
                    "state": item.get("state", "active"),
                    "tags": item.get("tags", []),
                    "evidence": item.get("evidence", []),
                    "skill": "evo-qa",
                },
                "created_at": item.get("created_at") or _utcnow_iso(),
            })

    out_file = out_dir / "memories.json"
    out_file.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False))

    readme = out_dir / "README.md"
    readme.write_text(
        "# Evo QA → mem0 export\n\n"
        f"Exported {len(entries)} memory entries from project "
        f"`{workspace.project}` at {_utcnow_iso()}.\n\n"
        "## How to import\n\n"
        "```bash\n"
        "# Using the mem0 CLI (recommended):\n"
        "mem0 import memories.json --agent-id evo-qa\n\n"
        "# Or programmatically:\n"
        "from mem0 import Memory\n"
        "import json\n"
        "m = Memory()\n"
        "for e in json.load(open('memories.json')):\n"
        "    m.add(e['memory'], user_id=e['user_id'], "
        "agent_id=e['agent_id'], metadata=e['metadata'])\n"
        "```\n"
    )
    return {"ok": True, "format": "mem0", "out_dir": str(out_dir),
            "count": len(entries), "out_file": str(out_file)}


def _summarize_for_mem0(kind: str, item: Dict[str, Any]) -> str:
    """Render a brain entry as a single human-readable memory string.

    mem0 expects natural-language strings, not structured rows. We
    keep them short (one line) and prefix with the kind so retrieval
    can filter.
    """
    if kind == "page":
        title = item.get("title", "") or item.get("path", "")
        url = item.get("url", "")
        return f"[page] {title} ({url})".strip()
    if kind == "transition":
        return (f"[transition] {item.get('from','?')} -> "
                f"{item.get('to','?')} via {item.get('action','')}")
    if kind == "observation":
        return f"[observation] {item.get('claim') or item.get('text','')}"
    if kind == "question":
        return f"[question] {item.get('text','')}"
    if kind == "contradiction":
        return (f"[contradiction] {item.get('left','?')} vs "
                f"{item.get('right','?')}")
    return ""


def _export_raw_json(workspace, out_dir: Path) -> Dict[str, Any]:
    """Raw brain dump: copy every YAML file under brain/system and
    brain/business, plus indices, into one JSON for archival."""
    import yaml
    bundle: Dict[str, Any] = {
        "exportedAt": _utcnow_iso(),
        "project": workspace.project,
        "files": {},
    }
    for sub in ("system", "business"):
        d = workspace.brain_dir / sub
        if not d.exists():
            continue
        for yml in d.glob("*.yml"):
            try:
                bundle["files"][f"{sub}/{yml.name}"] = yaml.safe_load(
                    yml.read_text()) or []
            except Exception as e:
                bundle["files"][f"{sub}/{yml.name}"] = {"error": str(e)}
    out_file = out_dir / "brain.json"
    out_file.write_text(json.dumps(bundle, indent=2, ensure_ascii=False))
    return {"ok": True, "format": "json", "out_dir": str(out_dir),
            "out_file": str(out_file),
            "files": list(bundle["files"].keys())}
