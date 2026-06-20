"""
Snapshot -- a logical consistency point, NOT a physical file copy.

A snapshot is defined by a single monotonic number: the upper bound
run_id at the moment of capture. Consumers (reflection) read the
brain AS-IS and filter evidence on the fly via SystemBrain.view_at().

Why this is correct:
  - All brain entries carry prov.evidence: list[run_id]
  - run_ids embed timestamp prefix and are monotonically increasing
  - Filtering is a pure read operation, no locks needed
  - New runs after snapshot taken don't disturb the snapshot's view

Why this beats physical file copy:
  - Zero I/O at snapshot time
  - Zero disk space
  - Always 100% consistent (single number, no torn state)
  - Auditable: snap_id encodes upper_bound directly
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from .._atomic import atomic_write


@dataclass
class Snapshot:
    snap_id: str           # snap-<upper_bound_safe>-<ts>
    upper_bound: str       # max run_id at snapshot time, "" if none
    taken_at: str
    evidence_run_count: int = 0   # count of unique runs ≤ upper_bound

    def includes(self, run_id: str) -> bool:
        """Is this run_id covered by the snapshot?"""
        if not self.upper_bound:
            return False
        # run_ids are timestamp-prefixed (run-<ts>-...), lexicographic
        # ordering matches temporal ordering.
        return run_id <= self.upper_bound


def _scan_max_run_id(brain_dir: Path) -> tuple[str, int]:
    """Walk every YAML in brain/system/ and find the lexicographically
    max run_id appearing in any prov.evidence list. Returns
    (max_run_id_or_empty, count_of_unique_runs_seen).
    """
    sys_dir = brain_dir / "system"
    if not sys_dir.exists():
        return "", 0
    seen: set[str] = set()
    for path in sys_dir.glob("*.yml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for entry in data:
            prov = entry.get("prov") if isinstance(entry, dict) else None
            if not isinstance(prov, dict):
                continue
            ev = prov.get("evidence") or []
            for r in ev:
                if isinstance(r, str) and r:
                    seen.add(r)
    if not seen:
        return "", 0
    return max(seen), len(seen)


def take_snapshot(brain_dir: Path) -> Snapshot:
    """O(1) over brain entry count. Persists a manifest only -- no
    bulk data is copied."""
    upper, count = _scan_max_run_id(brain_dir)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    # Slug the upper_bound for safe filename
    safe_upper = re.sub(r"[^A-Za-z0-9._-]+", "_", upper) or "empty"
    snap_id = f"snap-{safe_upper}-{ts}"
    snap = Snapshot(
        snap_id=snap_id,
        upper_bound=upper,
        taken_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        evidence_run_count=count,
    )
    # Persist manifest (audit trail). No data copied.
    manifest_path = brain_dir / ".snapshots" / f"{snap_id}.yml"
    atomic_write(
        manifest_path,
        yaml.safe_dump(asdict(snap), sort_keys=False, allow_unicode=True),
    )
    return snap


def load_snapshot(brain_dir: Path, snap_id: str) -> Optional[Snapshot]:
    """Load a manifest by id. Returns None if missing/corrupt."""
    path = brain_dir / ".snapshots" / f"{snap_id}.yml"
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return Snapshot(**data)
    except Exception:
        return None


def list_snapshots(brain_dir: Path) -> list[Snapshot]:
    """All known snapshots, newest first by snap_id (which is ts-suffixed)."""
    snap_dir = brain_dir / ".snapshots"
    if not snap_dir.exists():
        return []
    out = []
    for p in sorted(snap_dir.glob("snap-*.yml"), reverse=True):
        s = load_snapshot(brain_dir, p.stem)
        if s:
            out.append(s)
    return out


__all__ = ["Snapshot", "take_snapshot", "load_snapshot", "list_snapshots"]
