"""
RunBus -- the async sidecar for reverse-feedback.

  +-----------+ publish(event)   +-------------------+
  | main flow | ---------------> | events.jsonl      |
  +-----------+  O_APPEND/<4KB   |  (append-only)    |
                                 +---------+---------+
                                           |
                              +------------+------------+
                              |            |            |
                          per-sink     per-sink     per-sink
                          cursor       cursor       cursor
                              |            |            |
                              v            v            v
                         ExtractorSink  LearnSink   ...

Concurrency model: SINGLE-WRITER on events.jsonl (only main process
appends). Sinks are READERS who maintain their own byte-offset cursor.
Lock-free under the assumption that each event line is < 4000 bytes
(O_APPEND atomicity guarantee on Linux).

Failure model:
  - publish() never raises. If write fails, log warning; main flow
    continues. Reverse-feedback for that event is lost; main flow SLA
    is preserved.
  - A sink that throws while handling an event has the event sent to
    dead-letter; cursor advances; next event is processed.
  - A sink that hangs is the sink runner's problem (timeout enforced
    in core/sinks/runner.py, not here).

State on disk:
  brain/.bus/events.jsonl               # main flow appends here
  brain/.bus/cursors/<sink_name>.yml    # per-sink offset
  brain/.bus/dead-letter/<sink>.jsonl   # events that permanently failed
  brain/.bus/archived/events-<ts>.jsonl # rotated logs
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional, Iterator

import yaml

from ._atomic import atomic_write, append_event, safe_read
from .events import Event


# Rotation thresholds
ROTATE_SIZE_BYTES = 50 * 1024 * 1024     # 50 MB
ROTATE_AGE_DAYS = 30
# Probability of running a rotation check on each publish (1 in N)
ROTATE_CHECK_DENOM = 100


@dataclass
class SinkCursor:
    """Per-sink processing position. atomic_write'd, single-writer
    by the sink runner that owns it."""
    sink_name: str
    last_processed_offset: int = 0
    last_processed_event_id: str = ""
    last_success_at: str = ""
    processed_count: int = 0
    failed_count: int = 0           # transient retries
    dead_letter_count: int = 0      # permanent failures
    rotation_count: int = 0         # how many rotations we've followed


class RunBus:
    """The bus singleton. One instance per process; cheap to construct
    so just instantiate per use site."""

    def __init__(self, brain_dir: Path):
        self.brain_dir = brain_dir
        self.bus_dir = brain_dir / ".bus"
        self.events_path = self.bus_dir / "events.jsonl"
        self.cursors_dir = self.bus_dir / "cursors"
        self.dead_letter_dir = self.bus_dir / "dead-letter"
        self.archived_dir = self.bus_dir / "archived"

    # ------------------------------------------------------------------
    # Producer side (called by main flow)
    # ------------------------------------------------------------------

    def publish(self, event: Event) -> bool:
        """Append event to events.jsonl. NEVER raises.

        Returns True on success, False if the event was lost. Caller
        should not branch on the return value -- main flow continues
        regardless. The bool exists for tests and observability.
        """
        try:
            line = event.to_jsonl()
        except Exception as e:
            print(f"[run_bus] event serialization failed: {e}",
                  file=sys.stderr)
            return False

        try:
            append_event(self.events_path, line)
        except Exception as e:
            print(f"[run_bus] publish failed for {event.id}: {e}",
                  file=sys.stderr)
            return False

        # Probabilistic rotation check -- cheap most of the time.
        try:
            if (event.ts_ns % ROTATE_CHECK_DENOM) == 0:
                self.maybe_rotate()
        except Exception as e:
            print(f"[run_bus] rotation check failed: {e}", file=sys.stderr)

        return True

    # ------------------------------------------------------------------
    # Consumer side (called by sink runners)
    # ------------------------------------------------------------------

    def tail(self, cursor: SinkCursor) -> Iterator[tuple[dict, int]]:
        """Yield (event_dict, offset_after) for each new event past
        the cursor's offset. Caller advances cursor.last_processed_offset
        to offset_after AFTER successfully handling the event.

        If events.jsonl doesn't exist yet, yields nothing.
        If cursor offset > file size (e.g. file truncated/rotated),
        we treat as end-of-stream; runner should detect rotation
        separately.
        """
        if not self.events_path.exists():
            return
        size = self.events_path.stat().st_size
        if cursor.last_processed_offset > size:
            return  # rotation happened; runner should reset

        with open(self.events_path, "rb") as f:
            f.seek(cursor.last_processed_offset)
            while True:
                raw = f.readline()
                if not raw:
                    break
                offset_after = f.tell()
                try:
                    event = json.loads(raw.decode("utf-8"))
                except Exception:
                    # corrupt line; skip but advance offset to avoid
                    # infinite loop on malformed entry.
                    cursor.last_processed_offset = offset_after
                    continue
                yield event, offset_after

    # ------------------------------------------------------------------
    # Cursor I/O
    # ------------------------------------------------------------------

    def load_cursor(self, sink_name: str) -> SinkCursor:
        path = self.cursors_dir / f"{sink_name}.yml"
        raw = safe_read(path, "")
        if not raw:
            return SinkCursor(sink_name=sink_name)
        try:
            data = yaml.safe_load(raw) or {}
            return SinkCursor(**data)
        except Exception as e:
            print(f"[run_bus] cursor for {sink_name} corrupt, resetting: {e}",
                  file=sys.stderr)
            return SinkCursor(sink_name=sink_name)

    def save_cursor(self, cursor: SinkCursor) -> None:
        path = self.cursors_dir / f"{cursor.sink_name}.yml"
        atomic_write(
            path,
            yaml.safe_dump(asdict(cursor), sort_keys=False, allow_unicode=True),
        )

    def list_cursors(self) -> list[SinkCursor]:
        if not self.cursors_dir.exists():
            return []
        out = []
        for p in sorted(self.cursors_dir.glob("*.yml")):
            out.append(self.load_cursor(p.stem))
        return out

    def write_dead_letter(self, sink_name: str, event: dict,
                          error: str) -> None:
        path = self.dead_letter_dir / f"{sink_name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "event": event,
            "error": error,
            "ts_ns": time.time_ns(),
        }
        # Dead-letter writes don't need atomic rename (append + fsync).
        # Lines may exceed 4KB here; we use a plain open to bypass the
        # append_event size check (dead-letter is diagnostic, not critical
        # for atomic append guarantees).
        line = json.dumps(record, ensure_ascii=False)
        if "\n" in line:
            line = line.replace("\n", " ")
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------

    def maybe_rotate(self) -> Optional[Path]:
        """Rotate events.jsonl if size/age threshold met AND it's safe.

        Safety = ALL known sinks have processed past current end-of-file.
        If any sink lags, we log and skip rotation. Better to grow the
        file than silently lose events.

        Returns the archived path if rotated, None otherwise.
        """
        if not self.events_path.exists():
            return None
        size = self.events_path.stat().st_size
        if size == 0:
            return None

        size_ok = size > ROTATE_SIZE_BYTES
        age_secs = time.time() - self.events_path.stat().st_mtime
        age_ok = age_secs > ROTATE_AGE_DAYS * 86400
        if not (size_ok or age_ok):
            return None

        cursors = self.list_cursors()
        if not cursors:
            # No sinks registered; safe to rotate (no one cares).
            return self._do_rotate(cursors)

        laggards = [c for c in cursors if c.last_processed_offset < size]
        if laggards:
            names = [c.sink_name for c in laggards]
            print(f"[run_bus] rotation deferred: sinks lagging: {names}",
                  file=sys.stderr)
            return None

        return self._do_rotate(cursors)

    def _do_rotate(self, cursors: list[SinkCursor]) -> Path:
        from datetime import datetime
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        archived = self.archived_dir / f"events-{ts}.jsonl"
        archived.parent.mkdir(parents=True, exist_ok=True)
        import os as _os
        _os.replace(self.events_path, archived)
        # New empty file
        self.events_path.touch()
        # Reset cursors
        for c in cursors:
            c.last_processed_offset = 0
            c.rotation_count += 1
            self.save_cursor(c)
        print(f"[run_bus] rotated -> {archived.name}, "
              f"reset {len(cursors)} cursor(s)", file=sys.stderr)
        return archived

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        cursors = self.list_cursors()
        size = (self.events_path.stat().st_size
                if self.events_path.exists() else 0)
        return {
            "events_path": str(self.events_path),
            "events_size_bytes": size,
            "sinks": [
                {
                    "name": c.sink_name,
                    "offset": c.last_processed_offset,
                    "lag_bytes": max(0, size - c.last_processed_offset),
                    "processed": c.processed_count,
                    "dead_letter": c.dead_letter_count,
                    "last_success_at": c.last_success_at,
                }
                for c in cursors
            ],
            "rotation_size_threshold": ROTATE_SIZE_BYTES,
            "rotation_age_days": ROTATE_AGE_DAYS,
        }


__all__ = [
    "RunBus", "SinkCursor",
    "ROTATE_SIZE_BYTES", "ROTATE_AGE_DAYS",
]
