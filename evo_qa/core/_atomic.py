"""
Atomic file primitives — the foundation everything else stands on.

Concurrency invariants (DO NOT VIOLATE):

  All file mutations in evo_qa MUST go through one of:
    - atomic_write(path, content)   for full-file replacement
    - append_event(path, line)      for events.jsonl O_APPEND

  No code outside this module is allowed to call open(path, "w").
  No code anywhere is allowed to call open(path, "r+").

Why: with single-writer + atomic rename, we eliminate the need for
file locks across our concurrent-process model (main + sinks +
scheduler). See memory/evo_qa/architecture-lesson-runbus.md.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Union

# O_APPEND is atomic for writes < PIPE_BUF on POSIX. Linux PIPE_BUF
# is 4096. Single events MUST stay under this for our lock-free
# guarantee to hold. Caller can pass any size; we assert.
PIPE_BUF_SAFE = 4000  # leave a little slack under 4096


def atomic_write(path: Union[str, Path], content: Union[str, bytes]) -> None:
    """Crash-safe full-file write.

    Sequence:
      1. write content to <path>.tmp
      2. fsync the tmp file
      3. os.replace(tmp, path)   -- atomic on both POSIX and Windows

    After return: <path> contains either the previous content or the new
    content, never partial. Safe for concurrent readers (they always see
    one consistent version).
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Per-process unique tmp so concurrent writers don't trample each
    # other's staging file. (race seen in test_decoupled C2.)
    tmp = p.with_suffix(p.suffix + f".tmp.{os.getpid()}.{os.urandom(4).hex()}")

    if isinstance(content, str):
        data = content.encode("utf-8")
    else:
        data = content

    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, p)  # atomic; last writer wins (acceptable: caller
                        # is responsible for read-modify-write merge)


def append_event(events_path: Union[str, Path], line: str) -> None:
    """Append a single line to an event log. Lock-free safe IF line < 4KB.

    Uses O_APPEND which guarantees atomicity for writes under PIPE_BUF.
    Each line ends in '\\n'; caller should not include one.
    """
    if "\n" in line:
        raise ValueError("event lines must not contain newlines")
    payload = (line + "\n").encode("utf-8")
    if len(payload) > PIPE_BUF_SAFE:
        raise ValueError(
            f"event too large ({len(payload)} bytes); "
            f"keep events under {PIPE_BUF_SAFE} bytes for atomic append"
        )

    p = Path(events_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


def safe_read(path: Union[str, Path], default: str = "") -> str:
    """Read a file, return default if missing. Never partial because
    writers use atomic_write."""
    p = Path(path)
    if not p.exists():
        return default
    return p.read_text(encoding="utf-8")


__all__ = ["atomic_write", "append_event", "safe_read", "PIPE_BUF_SAFE"]
