# Architecture Lesson: Why RunBus Decoupling

> A retrospective on a near-disaster, written so future-us doesn't repeat it.

## The setup

Earlier in v1.0 development we had a tightly-coupled flow:

```
cmd_run → execute tests → render report → ingest brain → run curator → run reflection → return
```

It worked. Tests ran, reports rendered, the brain learned. **And then the brain caught fire.**

## What broke

A change in the brain extractor caused a YAML write to fail. Because the extractor was inline in the main flow, the entire `cmd_run` raised. The user saw their tests had passed visibly in the browser, but the CLI returned non-zero. They thought their tests broke. They started investigating their tests. Their tests were fine.

The reverse-feedback machinery — the part that makes us *grow* — was directly threatening the part that delivers user value.

This is the failure mode every well-meaning system eventually hits: **the bonus feature became the load-bearing wall.**

## The principle, stated plainly

> **The main flow must stay solid. Reverse feedback is a bonus, never a liability.**

Concretely:

- A user running tests should never know whether the brain is healthy.
- A failure in the curator should never affect tomorrow's test run.
- A bug in an LLM reflection prompt should never delay a CI pipeline.
- Reverse-feedback components must be **opt-in for failures** — they fail in their own corner.

## How we got there

Four design choices:

### 1. Sink vs Job — the binary distinction

Every reverse-feedback consumer is either a **Sink** or a **Job**. Picked by one question:

> *Can I do my work by looking at one run?*

- Yes → **Sink** (per-run reactive, idempotent, fast).
  Examples: `ExtractorSink` (parse this run, update brain).
- No, I need a batch / time window → **Job** (scheduled, takes a snapshot).
  Examples: `CuratorJob` (scan all entries for staleness), `ReflectionJob` (look at N runs of evidence and propose business claims).

Don't blur the line. A sink that secretly waits for "a few more runs" is a job in disguise — it will leak run-time into the wrong place.

### 2. Cursors on disk, snapshots are run_id upper bounds

State lives on disk as **cursors**, not in memory:

- Each sink has `brain/.bus/cursors/<sink>.yml`
- Each job has `brain/.scheduler/<job>_cursor.yml`

Snapshots are **zero-copy**: a single `run_id` upper bound. `view_at(snap)` is a lazy filter at read time — `evidence.run_id <= upper_bound` and you have a frozen view, no clone.

This is the single most important simplification. We initially over-engineered "snapshot the brain to a folder" before realizing the cheap thing works.

### 3. Single writer + atomic rename, not locks

YAML files are mutated through **one writer, atomic rename**:

```python
def atomic_write(path, content):
    tmp = path.with_suffix(...".tmp." + pid + random)
    write(tmp); fsync(tmp)
    os.replace(tmp, path)  # atomic
```

Where multiple processes need to write the same file (extractor + curator both touch a brain entry's `revision_history`), we use a **mediator** — `BrainWriter` — that holds the **field-ownership matrix**:

| Field | Owner |
|---|---|
| `id`, `claim`, `evidence`, `confidence`, `last_verified_*` | `ExtractorSink` |
| `review_state` transitions, `_archived/` directory | `CuratorJob` |
| `revision_history` | both, deduplicated by `(actor, ts_ns)` |

Locks are a code smell for our scale. Atomic file ops are sufficient.

### 4. Events small, append atomic

`events.jsonl` is appended via `O_APPEND` (atomic on Linux for writes < `PIPE_BUF` = 4KB). We enforce a **3500-byte soft cap** on events with a hard error at 4000. Events that need more data reference paths to files written separately via `atomic_write`.

This means concurrent publishers from any number of processes can append to the bus without coordination. Lock-free.

## The fault-injection gauntlet

We proved the SLA with 12 tests in `scripts/test_decoupled.py`:

- **A1–A3**: main-flow SLA — sink throws / event oversized / dir unwritable → main flow zero impact
- **B1–B2**: idempotency — replay does not drift; mid-handle crash recoverable
- **C1–C2**: concurrency — 4 processes × 25 events all intact; 3 concurrent BrainWriters no torn YAML
- **D1–D3**: cursor robustness — corrupt cursor self-resets; torn JSONL line skipped; failure isolated per sink
- **E1–E2**: scheduler — Curator state machine; snapshot view does not leak future evidence

12/12 green in v1.0.2.

## The lesson, generalized

When you add a "learning loop" / "feedback mechanism" / "telemetry" to a working system:

1. **First answer**: can this thing fail without anyone noticing? If no, you haven't decoupled enough.
2. **Second answer**: where does state live during a crash? If "in memory", you don't have decoupling, you have a delay.
3. **Third answer**: who owns each field? If "everyone", you have a race waiting to happen.
4. **Fourth answer**: what's the smallest thing that could fail here? Make sure that smallest thing has a corner to fail in (dead-letter, retry budget, escalation log) and never bubbles up.

Reverse-feedback is too valuable to skip. But it's also too valuable to let it crash the main flow.

Decoupled architectures aren't about scale — they're about **respecting the difference between what users paid for and what we built for ourselves**.
