"""
Sink runner -- drives sinks against the RunBus.

Two operating modes:

  inline-detached:
    Main flow's `cmd_run_v1` calls `spawn_inline()` after `bus.publish()`.
    It fork+exec's a subprocess that runs `process_backlog_once()` and
    exits. Main flow does not wait.

  deferred:
    No subprocess. Backlog accumulates in events.jsonl. A periodic
    trigger (cron, manual `qa health --process-backlog`, scheduler tick)
    calls `process_backlog_once()` synchronously.

Per-event handling pseudocode:

    for sink in registered_sinks:
        cur = bus.load_cursor(sink.name)
        for event, offset_after in bus.tail(cur):
            if not sink.matches(event):
                cur.last_processed_offset = offset_after
                bus.save_cursor(cur)
                continue
            try:
                sink.handle(event)
                cur.last_processed_offset = offset_after
                cur.last_processed_event_id = event['id']
                cur.processed_count += 1
                cur.last_success_at = utc_now()
            except SinkRetryable:
                break          # transient: stop, retry later
            except Exception as e:
                bus.write_dead_letter(sink.name, event, repr(e))
                cur.last_processed_offset = offset_after
                cur.dead_letter_count += 1
            bus.save_cursor(cur)
"""
from __future__ import annotations

import os
import sys
import subprocess
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .base import Sink, SinkRetryable
from ..run_bus import RunBus


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def process_backlog_once(bus: RunBus, sinks: Iterable[Sink],
                         *, max_events_per_sink: int = 1000) -> dict:
    """Drain pending events for each sink. Returns a summary dict.

    Synchronous; safe to call from any process. Each sink is isolated
    by try/except -- one sink's failure does not affect others.
    """
    summary = {"sinks": {}, "started_at": _utc_now()}

    for sink in sinks:
        sink_summary = {
            "processed": 0,
            "dead_lettered": 0,
            "skipped_unmatched": 0,
            "stopped_retryable": False,
            "error": None,
        }
        try:
            cursor = bus.load_cursor(sink.name)
            count = 0
            for event, offset_after in bus.tail(cursor):
                if count >= max_events_per_sink:
                    break
                count += 1

                if not sink.matches(event):
                    cursor.last_processed_offset = offset_after
                    bus.save_cursor(cursor)
                    sink_summary["skipped_unmatched"] += 1
                    continue

                try:
                    sink.handle(event)
                    cursor.last_processed_offset = offset_after
                    cursor.last_processed_event_id = event.get("id", "")
                    cursor.processed_count += 1
                    cursor.last_success_at = _utc_now()
                    bus.save_cursor(cursor)
                    sink_summary["processed"] += 1
                except SinkRetryable:
                    sink_summary["stopped_retryable"] = True
                    break
                except Exception as e:
                    err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
                    bus.write_dead_letter(sink.name, event, err)
                    cursor.last_processed_offset = offset_after
                    cursor.dead_letter_count += 1
                    bus.save_cursor(cursor)
                    sink_summary["dead_lettered"] += 1
        except Exception as e:
            # Cursor I/O or other infra failure -- isolate per-sink.
            sink_summary["error"] = f"{type(e).__name__}: {e}"

        summary["sinks"][sink.name] = sink_summary

    summary["finished_at"] = _utc_now()
    return summary


# ---------------------------------------------------------------------------
# inline-detached spawn
# ---------------------------------------------------------------------------

def spawn_inline(brain_dir: Path) -> int:
    """Fork+exec a subprocess that processes the backlog and exits.

    Returns the pid. Main flow does NOT wait. If spawn fails, log and
    return 0; the next bus.publish or `qa health` will catch up.
    """
    cmd = [
        sys.executable,
        "-m",
        "evo_qa.core.sinks.runner",
        str(brain_dir),
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,   # detach from parent's session
        )
        return proc.pid
    except Exception as e:
        print(f"[sinks.runner] spawn_inline failed: {e}", file=sys.stderr)
        return 0


# ---------------------------------------------------------------------------
# Default sink registry
# ---------------------------------------------------------------------------

def default_sinks(brain_dir: Path) -> list[Sink]:
    """All sinks shipped with v1.0.2. Add new sinks here."""
    from .extractor_sink import ExtractorSink
    return [ExtractorSink(brain_dir)]


# ---------------------------------------------------------------------------
# CLI entry: `python -m evo_qa.core.sinks.runner <brain_dir>`
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python -m evo_qa.core.sinks.runner <brain_dir>",
              file=sys.stderr)
        return 2
    brain_dir = Path(argv[1])
    bus = RunBus(brain_dir)
    sinks = default_sinks(brain_dir)
    summary = process_backlog_once(bus, sinks)
    # Quietly succeed; main flow doesn't watch our exit code.
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
