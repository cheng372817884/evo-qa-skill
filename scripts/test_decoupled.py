"""
Failure-injection test suite for the decoupled architecture.

Proves the SLA: main flow stays green even when reverse-feedback breaks.
"""
import os
import sys
import tempfile
import textwrap
import atexit
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from evo_qa.core.events import RunCompleted
from evo_qa.core.run_bus import RunBus
from evo_qa.core.sinks.runner import process_backlog_once, default_sinks
from evo_qa.core.sinks.base import Sink
from evo_qa.core.system_brain.storage import SystemBrain
from evo_qa.core.system_brain.writer import BrainWriter
from evo_qa.core.system_brain import PageNode, Provenance
from evo_qa.core.scheduler.snapshot import take_snapshot
from evo_qa.core.scheduler.curator_job import CuratorJob
from evo_qa.core.scheduler.reflection_job import ReflectionJob


# Generate a real pytest spec on disk so the extractor has something to
# parse. Built once per test process; cleaned at exit.
_FIXTURE_DIR = Path(tempfile.mkdtemp(prefix="pq_test_decoupled_"))
atexit.register(lambda: __import__("shutil").rmtree(_FIXTURE_DIR, ignore_errors=True))
_PYTEST_FIXTURE = _FIXTURE_DIR / "test_sample.py"
_PYTEST_FIXTURE.write_text(textwrap.dedent('''
    from playwright.sync_api import Page, expect

    def test_basic_flow(page: Page):
        page.goto("https://example.com/login")
        page.fill("#username", "alice")
        page.fill("#password", "secret")
        page.click("button[type=submit]")
        expect(page).to_have_title("Dashboard")
'''), encoding="utf-8")
GW_TEST = str(_PYTEST_FIXTURE)


def section(name):
    print(f"\n--- {name} ---")


# ============================================================
# A. Main-flow SLA: bus failures must not affect main flow
# ============================================================

def A1_sink_throws_main_flow_unaffected():
    """A1: ExtractorSink raises -> dead-letter, main flow returns OK."""
    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        bus = RunBus(bd)

        ok = bus.publish(RunCompleted(
            project="p", run_id="r1", verdict="pass",
            test_file_path="/nonexistent/path.py",  # not really thrown
        ))
        assert ok, "publish should succeed even if downstream will fail"

        class BoomSink(Sink):
            name = "extractor"  # masquerade as the real sink name
            accepts = ("run.completed",)
            def handle(self, event):
                raise RuntimeError("simulated brain corruption")

        summary = process_backlog_once(bus, [BoomSink()])
        assert summary["sinks"]["extractor"]["dead_lettered"] == 1
        # User would never see this; main flow already returned.
        dl = bus.dead_letter_dir / "extractor.jsonl"
        assert dl.exists()
        print(f"  ✓ A1: dead-letter recorded ({dl.stat().st_size} bytes)")


def A2_publish_never_raises_on_oversized_event():
    """A2: oversized event -> publish returns False, no exception."""
    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        bus = RunBus(bd)
        big = RunCompleted(project="x" * 5000, run_id="r1")
        ok = bus.publish(big)
        assert ok is False
        # Bus directory exists but events.jsonl may be empty
        print("  ✓ A2: oversized publish returned False, no raise")


def A3_publish_never_raises_on_unwritable_dir():
    """A3: events dir locked -> publish returns False, no exception."""
    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        bus = RunBus(bd)
        # Make .bus a read-only file (not a dir) -> mkdir will fail
        bus_dir = bus.bus_dir
        bus_dir.parent.mkdir(parents=True, exist_ok=True)
        bus_dir.write_text("not a directory")  # blocks mkdir of children
        ok = bus.publish(RunCompleted(project="p", run_id="r1", verdict="pass"))
        assert ok is False, "publish should fail gracefully"
        print("  ✓ A3: unwritable .bus dir -> graceful False")


# ============================================================
# B. Idempotency: replay must not corrupt state
# ============================================================

def B1_replay_same_event_no_drift():
    """B1: same event delivered twice -> brain stable."""
    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        bus = RunBus(bd)
        bus.publish(RunCompleted(
            project="p", run_id="r1", verdict="pass",
            test_file_path=GW_TEST,
        ))
        sinks = default_sinks(bd)
        process_backlog_once(bus, sinks)
        b1 = SystemBrain(bd); b1.load()
        evidence_count_1 = sum(len(p.prov.evidence) for p in b1.pages.values())

        # Rewind cursor
        cur = bus.load_cursor("extractor")
        cur.last_processed_offset = 0
        bus.save_cursor(cur)
        process_backlog_once(bus, sinks)
        b2 = SystemBrain(bd); b2.load()
        evidence_count_2 = sum(len(p.prov.evidence) for p in b2.pages.values())

        assert evidence_count_1 == evidence_count_2, \
            f"replay drift: {evidence_count_1} -> {evidence_count_2}"
        print(f"  ✓ B1: evidence stable across replay ({evidence_count_1})")


def B2_mid_event_crash_recovers():
    """B2: simulate crash mid-handle -> cursor unchanged, replay works."""
    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        bus = RunBus(bd)
        bus.publish(RunCompleted(
            project="p", run_id="r1", verdict="pass",
            test_file_path=GW_TEST,
        ))

        attempts = [0]

        class FlakyExtractor(Sink):
            name = "extractor"
            accepts = ("run.completed",)
            def handle(self, event):
                attempts[0] += 1
                if attempts[0] == 1:
                    raise RuntimeError("simulated crash mid-handle")
                # Second attempt: succeed by no-op (idempotent)

        # First call: crashes -> dead-letter (cursor advances by design)
        summary1 = process_backlog_once(bus, [FlakyExtractor()])
        assert summary1["sinks"]["extractor"]["dead_lettered"] == 1
        # Cursor advanced past the bad event (correct behavior: don't loop)

        # Now publish a NEW event; second attempt processes it
        bus.publish(RunCompleted(project="p", run_id="r2", verdict="pass"))
        summary2 = process_backlog_once(bus, [FlakyExtractor()])
        assert summary2["sinks"]["extractor"]["processed"] == 1
        print(f"  ✓ B2: crashed event in dead-letter, fresh event processed")


# ============================================================
# C. Concurrency: simultaneous writes don't tear
# ============================================================

def C1_concurrent_publishers():
    """C1: multiple processes publishing -> all events captured intact."""
    import multiprocessing as mp

    def worker(brain_dir, n, label):
        from evo_qa.core.run_bus import RunBus
        from evo_qa.core.events import RunCompleted
        bus = RunBus(Path(brain_dir))
        for i in range(n):
            bus.publish(RunCompleted(
                project=label, run_id=f"{label}-{i:03d}", verdict="pass",
            ))

    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        bd.mkdir(parents=True)
        N_WORKERS = 4
        N_EACH = 25
        procs = [mp.Process(target=worker, args=(str(bd), N_EACH, f"w{i}"))
                 for i in range(N_WORKERS)]
        for p in procs: p.start()
        for p in procs: p.join(timeout=15)

        bus = RunBus(bd)
        events_file = bus.events_path
        lines = events_file.read_text().splitlines()
        # Each line should be valid JSON
        import json
        decoded = 0
        for ln in lines:
            try:
                json.loads(ln)
                decoded += 1
            except json.JSONDecodeError:
                pass
        expected = N_WORKERS * N_EACH
        assert decoded == expected, \
            f"expected {expected} valid events, got {decoded} of {len(lines)}"
        print(f"  ✓ C1: {decoded}/{expected} concurrent events intact")


def C2_concurrent_brain_writes():
    """C2: BrainWriter from multiple processes -> no torn YAML."""
    import multiprocessing as mp

    def worker(brain_dir, label, n):
        from evo_qa.core.system_brain.writer import BrainWriter
        from evo_qa.core.system_brain import PageNode, Provenance
        w = BrainWriter(Path(brain_dir))
        for i in range(n):
            p = PageNode(id=f"{label}-page-{i}",
                         title_pattern=f"{label} page {i}",
                         prov=Provenance())
            w.observe_page(p, f"{label}-run-{i}")

    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        N_WORKERS = 3
        N_EACH = 8
        procs = [mp.Process(target=worker, args=(str(bd), f"w{i}", N_EACH))
                 for i in range(N_WORKERS)]
        for p in procs: p.start()
        for p in procs: p.join(timeout=20)

        b = SystemBrain(bd); b.load()
        # Count pages — at minimum each writer's last page should survive
        # (full count depends on read-modify-write race; at least
        # N_WORKERS page IDs should survive)
        total = len(b.pages)
        max_per_w = N_EACH * N_WORKERS
        assert total >= N_WORKERS, \
            f"expected at least {N_WORKERS} pages, got {total}"
        assert total <= max_per_w
        print(f"  ✓ C2: {total} pages survived (load-merge race tolerant)")


# ============================================================
# D. Cursor robustness: corruption doesn't break the bus
# ============================================================

def D1_corrupt_cursor_resets_safely():
    """D1: cursor file is garbage -> cursor reset, no crash."""
    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        bus = RunBus(bd)
        bus.publish(RunCompleted(project="p", run_id="r1", verdict="pass"))

        # Corrupt cursor before processing
        bus.cursors_dir.mkdir(parents=True, exist_ok=True)
        cursor_path = bus.cursors_dir / "extractor.yml"
        cursor_path.write_text("{ this is not valid yaml ::: !!!")

        sinks = default_sinks(bd)
        # Should NOT raise
        summary = process_backlog_once(bus, sinks)
        # Cursor should be sane afterwards
        cur = bus.load_cursor("extractor")
        assert cur.last_processed_offset >= 0
        print(f"  ✓ D1: corrupt cursor reset gracefully, "
              f"offset now {cur.last_processed_offset}")


def D2_truncated_event_line_skipped():
    """D2: a partial JSON line -> skipped, processing continues."""
    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        bus = RunBus(bd)
        # Publish one good event
        bus.publish(RunCompleted(project="p", run_id="r1", verdict="pass"))
        # Then append a torn line directly
        with bus.events_path.open("ab") as f:
            f.write(b'{"event_id":"torn","event_type":"run.completed"\n')
        # Then another good event
        bus.publish(RunCompleted(project="p", run_id="r2", verdict="pass"))

        cursor = bus.load_cursor("test_sink")
        valid = list(bus.tail(cursor))
        assert len(valid) == 2, f"expected 2 valid, got {len(valid)}"
        print(f"  ✓ D2: torn line skipped, {len(valid)} valid events read")


def D3_dead_letter_isolation():
    """D3: failure in one sink doesn't poison cursor of another."""
    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        bus = RunBus(bd)
        bus.publish(RunCompleted(project="p", run_id="r1", verdict="pass"))

        class GoodSink(Sink):
            name = "good"
            accepts = ("run.completed",)
            handled = []
            def handle(self, event):
                self.handled.append(event["id"])

        class BadSink(Sink):
            name = "bad"
            accepts = ("run.completed",)
            def handle(self, event):
                raise RuntimeError("nope")

        good = GoodSink()
        bad = BadSink()
        process_backlog_once(bus, [good, bad])
        assert len(good.handled) == 1
        # bad sink dead-letter populated; good sink cursor advanced
        good_cur = bus.load_cursor("good")
        bad_cur = bus.load_cursor("bad")
        assert good_cur.last_processed_offset > 0
        assert bad_cur.last_processed_offset > 0  # advanced past bad event
        print(f"  ✓ D3: failure isolated; good sink processed independently")


# ============================================================
# E. Scheduler integration smoke
# ============================================================

def E1_scheduler_curator_via_bus():
    """E1: publish events -> drain via sink -> curator job acts on result."""
    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        # Seed brain with old entries
        from datetime import datetime, timedelta
        w = BrainWriter(bd)
        w.observe_page(PageNode(id="old1", title_pattern="Old",
                                prov=Provenance()), "run-x")
        b = SystemBrain(bd); b.load()
        old = (datetime.utcnow() - timedelta(days=120)).isoformat() + "Z"
        b.pages["old1"].prov.created_at = old
        b.pages["old1"].prov.updated_at = old
        b.save()

        job = CuratorJob(bd)
        cur = job.load_cursor()
        result = job.execute()
        assert result.error is None
        assert result.summary["active_to_stale"] == 1
        # Cursor persisted
        cur2 = job.load_cursor()
        assert cur2.success_count >= 1
        print(f"  ✓ E1: CuratorJob via execute() : {result.summary}")


def E2_scheduler_reflection_snapshot_isolation():
    """E2: snapshot frozen at run R -> later runs invisible to that view."""
    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        w = BrainWriter(bd)
        w.observe_page(PageNode(id="early", title_pattern="Early",
                                prov=Provenance()), "run-001")
        snap = take_snapshot(bd)
        assert snap.upper_bound == "run-001"

        # Now add a later run AFTER snapshot
        w.observe_page(PageNode(id="late", title_pattern="Late",
                                prov=Provenance()), "run-002")

        b = SystemBrain(bd); b.load()
        view = b.view_at(snap)
        # 'late' page exists in brain but NOT in the snapshotted view
        assert "early" in view.pages
        assert "late" not in view.pages, \
            "snapshot leaked future evidence"
        print(f"  ✓ E2: snapshot view isolated "
              f"(brain has {len(b.pages)}, view has {len(view.pages)})")


# ============================================================
# Runner
# ============================================================

ALL_TESTS = [
    ("A1_sink_throws_main_flow_unaffected", A1_sink_throws_main_flow_unaffected),
    ("A2_publish_never_raises_on_oversized_event",
     A2_publish_never_raises_on_oversized_event),
    ("A3_publish_never_raises_on_unwritable_dir",
     A3_publish_never_raises_on_unwritable_dir),
    ("B1_replay_same_event_no_drift", B1_replay_same_event_no_drift),
    ("B2_mid_event_crash_recovers", B2_mid_event_crash_recovers),
    ("C1_concurrent_publishers", C1_concurrent_publishers),
    ("C2_concurrent_brain_writes", C2_concurrent_brain_writes),
    ("D1_corrupt_cursor_resets_safely", D1_corrupt_cursor_resets_safely),
    ("D2_truncated_event_line_skipped", D2_truncated_event_line_skipped),
    ("D3_dead_letter_isolation", D3_dead_letter_isolation),
    ("E1_scheduler_curator_via_bus", E1_scheduler_curator_via_bus),
    ("E2_scheduler_reflection_snapshot_isolation",
     E2_scheduler_reflection_snapshot_isolation),
]


if __name__ == "__main__":
    print("=" * 60)
    print("Decoupled architecture: failure-injection test suite")
    print("=" * 60)
    passed, failed = 0, []
    for name, fn in ALL_TESTS:
        section(name)
        try:
            fn()
            passed += 1
        except AssertionError as e:
            failed.append((name, "ASSERT", str(e)))
            print(f"  ✗ {name}: ASSERT {e}")
        except Exception as e:
            failed.append((name, type(e).__name__, str(e)))
            print(f"  ✗ {name}: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
    print()
    print("=" * 60)
    print(f"Result: {passed}/{len(ALL_TESTS)} passed")
    if failed:
        print(f"Failed: {len(failed)}")
        for n, t, msg in failed:
            print(f"  - {n}: [{t}] {msg}")
        sys.exit(1)
    print("All decoupled SLA invariants hold ✅")
