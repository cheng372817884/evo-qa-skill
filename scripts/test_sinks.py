"""End-to-end tests for sinks + runner + bus integration."""
import os
import sys
import tempfile
import textwrap
import atexit
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from evo_qa.core.events import RunCompleted
from evo_qa.core.run_bus import RunBus
from evo_qa.core.sinks.runner import process_backlog_once, default_sinks
from evo_qa.core.sinks.base import Sink, SinkRetryable


# Generate a real pytest spec on disk for the legacy reverse-extractor.
# Without this, the extractor has no source and the brain stays empty.
# Built once per test process; auto-cleaned at exit.
_FIXTURE_DIR = Path(tempfile.mkdtemp(prefix="pq_test_sinks_"))
atexit.register(lambda: __import__("shutil").rmtree(_FIXTURE_DIR, ignore_errors=True))

_PYTEST_FIXTURE = _FIXTURE_DIR / "test_sample_login.py"
_PYTEST_FIXTURE.write_text(textwrap.dedent('''
    """A minimal pytest-playwright spec used as a brain-extraction fixture."""
    from playwright.sync_api import Page, expect

    def test_login_happy_path(page: Page):
        page.goto("https://example.com/login")
        page.fill("#username", "alice")
        page.fill("#password", "secret")
        page.click("button[type=submit]")
        expect(page).to_have_title("Dashboard")
'''), encoding="utf-8")

GW_TEST = str(_PYTEST_FIXTURE)


def test_extractor_processes_backlog():
    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        bus = RunBus(bd)
        bus.publish(RunCompleted(
            project="p", run_id="r1", verdict="pass",
            test_file_path=GW_TEST,
        ))
        bus.publish(RunCompleted(project="p", run_id="r2", verdict="pass"))

        summary = process_backlog_once(bus, default_sinks(bd))
        es = summary["sinks"]["extractor"]
        assert es["processed"] == 2
        assert es["dead_lettered"] == 0

        from evo_qa.core.system_brain.storage import SystemBrain
        b = SystemBrain(bd); b.load()
        assert len(b.pages) > 0
        print(f"✓ test_extractor_processes_backlog "
              f"(pages={len(b.pages)}, obs={len(b.observations)})")


def test_idempotent_replay():
    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        bus = RunBus(bd)
        bus.publish(RunCompleted(
            project="p", run_id="r1", verdict="pass",
            test_file_path=GW_TEST,
        ))
        sinks = default_sinks(bd)

        process_backlog_once(bus, sinks)
        from evo_qa.core.system_brain.storage import SystemBrain
        b1 = SystemBrain(bd); b1.load()
        evidence_before = sum(len(p.prov.evidence) for p in b1.pages.values())

        # Manually rewind cursor and replay
        cur = bus.load_cursor("extractor")
        cur.last_processed_offset = 0
        bus.save_cursor(cur)
        process_backlog_once(bus, sinks)

        b2 = SystemBrain(bd); b2.load()
        evidence_after = sum(len(p.prov.evidence) for p in b2.pages.values())
        assert evidence_before == evidence_after, \
            f"replay duplicated evidence: {evidence_before} -> {evidence_after}"
        print(f"✓ test_idempotent_replay (evidence stable at {evidence_after})")


def test_failure_isolation():
    """One bad sink does not affect others."""
    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        bus = RunBus(bd)
        bus.publish(RunCompleted(
            project="p", run_id="r1", verdict="pass",
            test_file_path=GW_TEST,
        ))

        class BoomSink(Sink):
            name = "boom"
            def handle(self, event):
                raise RuntimeError("simulated")

        sinks = [BoomSink(), default_sinks(bd)[0]]
        summary = process_backlog_once(bus, sinks)

        # boom dead-lettered the event
        assert summary["sinks"]["boom"]["dead_lettered"] == 1
        # extractor still processed it
        assert summary["sinks"]["extractor"]["processed"] == 1

        # Verify dead-letter file
        dl = bus.dead_letter_dir / "boom.jsonl"
        assert dl.exists()
        assert "simulated" in dl.read_text()

        # Verify cursors advanced independently
        cb = bus.load_cursor("boom")
        ce = bus.load_cursor("extractor")
        assert cb.last_processed_offset == ce.last_processed_offset
        assert cb.dead_letter_count == 1
        assert ce.processed_count == 1
        print("✓ test_failure_isolation")


def test_retryable_holds_cursor():
    """SinkRetryable must NOT advance the cursor."""
    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        bus = RunBus(bd)
        bus.publish(RunCompleted(project="p", run_id="r1", verdict="pass"))

        attempts = [0]
        class FlakySink(Sink):
            name = "flaky"
            def handle(self, event):
                attempts[0] += 1
                if attempts[0] == 1:
                    raise SinkRetryable("not yet")

        s = FlakySink()
        summary1 = process_backlog_once(bus, [s])
        assert summary1["sinks"]["flaky"]["stopped_retryable"]
        assert summary1["sinks"]["flaky"]["processed"] == 0
        # Cursor at 0 (didn't advance)
        cur = bus.load_cursor("flaky")
        assert cur.last_processed_offset == 0

        # Retry succeeds
        summary2 = process_backlog_once(bus, [s])
        assert summary2["sinks"]["flaky"]["processed"] == 1
        assert attempts[0] == 2
        print("✓ test_retryable_holds_cursor")


def test_unmatched_event_skipped_cleanly():
    """Sink with restrictive `accepts` skips events it doesn't handle
    but advances the cursor (otherwise it'd block forever)."""
    with tempfile.TemporaryDirectory() as d:
        bd = Path(d) / "brain"
        bus = RunBus(bd)
        bus.publish(RunCompleted(project="p", run_id="r1", verdict="pass"))

        class PickySink(Sink):
            name = "picky"
            accepts = ("never.fires",)
            def handle(self, event):
                raise AssertionError("should not be called")

        s = PickySink()
        summary = process_backlog_once(bus, [s])
        assert summary["sinks"]["picky"]["skipped_unmatched"] == 1
        assert summary["sinks"]["picky"]["processed"] == 0
        # Cursor advanced past the unmatched event
        cur = bus.load_cursor("picky")
        assert cur.last_processed_offset > 0
        print("✓ test_unmatched_event_skipped_cleanly")


if __name__ == "__main__":
    test_extractor_processes_backlog()
    test_idempotent_replay()
    test_failure_isolation()
    test_retryable_holds_cursor()
    test_unmatched_event_skipped_cleanly()
    print("\n✓ All sink tests passed (5/5)")
