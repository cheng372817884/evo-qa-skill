"""Smoke tests for events.py + run_bus.py."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from evo_qa.core.events import RunCompleted, RunFailed
from evo_qa.core.run_bus import RunBus, SinkCursor


def test_publish_and_tail():
    with tempfile.TemporaryDirectory() as d:
        bus = RunBus(Path(d) / "brain")
        # 1. publish 3 events
        for i in range(3):
            ok = bus.publish(RunCompleted(
                project="p", change_id="c", run_id=f"run-{i}",
                verdict="pass",
            ))
            assert ok
        assert bus.events_path.exists()
        size = bus.events_path.stat().st_size
        assert size > 0

        # 2. fresh sink reads all
        cur = bus.load_cursor("test_sink")
        assert cur.last_processed_offset == 0
        events = list(bus.tail(cur))
        assert len(events) == 3
        for e, off in events:
            assert e["type"] == "run.completed"
        # 3. cursor advance
        cur.last_processed_offset = events[-1][1]
        cur.processed_count = 3
        cur.last_success_at = "now"
        bus.save_cursor(cur)

        # 4. resume from cursor sees nothing
        cur2 = bus.load_cursor("test_sink")
        assert cur2.last_processed_offset == events[-1][1]
        assert cur2.processed_count == 3
        more = list(bus.tail(cur2))
        assert more == []

        # 5. publish 1 more, resume sees only that one
        bus.publish(RunCompleted(project="p", run_id="run-3", verdict="pass"))
        new = list(bus.tail(cur2))
        assert len(new) == 1
        assert new[0][0]["run_id"] == "run-3"

        print("✓ test_publish_and_tail")


def test_publish_never_raises():
    with tempfile.TemporaryDirectory() as d:
        bus = RunBus(Path(d) / "brain")
        # Force a serialization failure: oversized event
        big = RunCompleted(project="x" * 5000, run_id="r")
        ok = bus.publish(big)
        assert ok is False, "oversized should fail gracefully"
        # Bus didn't blow up, that's the point.
        print("✓ test_publish_never_raises")


def test_dead_letter():
    with tempfile.TemporaryDirectory() as d:
        bus = RunBus(Path(d) / "brain")
        bus.publish(RunCompleted(project="p", run_id="r1", verdict="pass"))
        bus.write_dead_letter(
            "test_sink",
            {"id": "evt-1", "type": "run.completed"},
            "boom: simulated",
        )
        dl = bus.dead_letter_dir / "test_sink.jsonl"
        assert dl.exists()
        content = dl.read_text()
        assert "evt-1" in content and "simulated" in content
        print("✓ test_dead_letter")


def test_corrupt_cursor_resets():
    with tempfile.TemporaryDirectory() as d:
        bus = RunBus(Path(d) / "brain")
        bus.cursors_dir.mkdir(parents=True)
        (bus.cursors_dir / "bad.yml").write_text("{this is: not valid: yaml: [[[")
        cur = bus.load_cursor("bad")
        assert cur.last_processed_offset == 0
        assert cur.sink_name == "bad"
        print("✓ test_corrupt_cursor_resets")


def test_stats():
    with tempfile.TemporaryDirectory() as d:
        bus = RunBus(Path(d) / "brain")
        for i in range(5):
            bus.publish(RunCompleted(project="p", run_id=f"r{i}", verdict="pass"))
        cur = SinkCursor(sink_name="s1", last_processed_offset=100,
                         processed_count=2)
        bus.save_cursor(cur)
        st = bus.stats()
        assert st["events_size_bytes"] > 0
        assert len(st["sinks"]) == 1
        assert st["sinks"][0]["name"] == "s1"
        assert st["sinks"][0]["lag_bytes"] > 0
        print(f"✓ test_stats  events_size={st['events_size_bytes']} "
              f"lag={st['sinks'][0]['lag_bytes']}")


def test_rotation_safe_when_all_caught_up():
    with tempfile.TemporaryDirectory() as d:
        bus = RunBus(Path(d) / "brain")
        for i in range(3):
            bus.publish(RunCompleted(project="p", run_id=f"r{i}", verdict="pass"))
        size = bus.events_path.stat().st_size

        # Simulate a fully-caught-up sink
        cur = SinkCursor(sink_name="s1", last_processed_offset=size,
                         processed_count=3)
        bus.save_cursor(cur)

        # Force rotation by lowering threshold via monkeypatch
        from evo_qa.core import run_bus as rb_mod
        old = rb_mod.ROTATE_SIZE_BYTES
        rb_mod.ROTATE_SIZE_BYTES = 10  # 10 bytes -> easy to exceed
        try:
            archived = bus.maybe_rotate()
        finally:
            rb_mod.ROTATE_SIZE_BYTES = old

        assert archived is not None and archived.exists()
        # cursor reset
        cur2 = bus.load_cursor("s1")
        assert cur2.last_processed_offset == 0
        assert cur2.rotation_count == 1
        # events.jsonl recreated empty
        assert bus.events_path.exists()
        assert bus.events_path.stat().st_size == 0
        print(f"✓ test_rotation_safe  archived={archived.name}")


def test_rotation_blocked_when_sink_lags():
    with tempfile.TemporaryDirectory() as d:
        bus = RunBus(Path(d) / "brain")
        for i in range(3):
            bus.publish(RunCompleted(project="p", run_id=f"r{i}", verdict="pass"))
        # A lagging sink
        cur = SinkCursor(sink_name="lazy", last_processed_offset=0)
        bus.save_cursor(cur)

        from evo_qa.core import run_bus as rb_mod
        old = rb_mod.ROTATE_SIZE_BYTES
        rb_mod.ROTATE_SIZE_BYTES = 10
        try:
            archived = bus.maybe_rotate()
        finally:
            rb_mod.ROTATE_SIZE_BYTES = old

        assert archived is None
        # events.jsonl still has its original content
        assert bus.events_path.stat().st_size > 0
        print("✓ test_rotation_blocked_when_sink_lags")


if __name__ == "__main__":
    test_publish_and_tail()
    test_publish_never_raises()
    test_dead_letter()
    test_corrupt_cursor_resets()
    test_stats()
    test_rotation_safe_when_all_caught_up()
    test_rotation_blocked_when_sink_lags()
    print("\n✓ All run_bus tests passed (7/7)")
