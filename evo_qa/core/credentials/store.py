"""
Credential store: the YAML index + entry model + scoring.

Layout on disk:

    <user_data_dir>/credentials.yaml
        version: 1
        entries:
          - id: <stable id>
            url: https://...
            username: <user-typed>
            label: "Free-form label"
            secret_backend: keyring | plaintext_file
            plaintext_password: <base64 string or null>
            uses: <int>
            last_used_at: <ISO 8601 UTC>
            created_at: <ISO 8601 UTC>
            projects: [list of project names that referenced it]
            notes: ""

Concurrency: all writes go through atomic_write. There is exactly
one writer expected (the human user via CLI), so no locks needed.
Multiple `qa:run` processes only ever READ + bump usage counters
through atomic read-modify-write; in the rare race the loser's
counter increment is dropped, which is acceptable.

This module NEVER imports keyring directly — that's backends.py.
"""
from __future__ import annotations

import math
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import yaml

from .._atomic import atomic_write


SCHEMA_VERSION = 1
INDEX_FILENAME = "credentials.yaml"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def user_data_dir() -> Path:
    """Return the per-user directory where Evo QA stores
    user-level state (credentials, future preferences).

    Override priority:
      1. $EVO_QA_HOME            (explicit override)
      2. Windows: %APPDATA%\\evo_qa
      3. macOS:   ~/Library/Application Support/evo_qa
      4. Linux:   $XDG_CONFIG_HOME/evo_qa or ~/.config/evo_qa
    """
    override = os.environ.get("EVO_QA_HOME")
    if override:
        return Path(override).expanduser().resolve()

    home = Path.home()
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "evo_qa"
        return home / "AppData" / "Roaming" / "evo_qa"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "evo_qa"
    # Linux / other POSIX
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "evo_qa"
    return home / ".config" / "evo_qa"


# ---------------------------------------------------------------------------
# Entry model
# ---------------------------------------------------------------------------

@dataclass
class CredentialEntry:
    id: str
    url: str
    username: str
    label: str = ""
    secret_backend: str = "keyring"            # or "plaintext_file"
    plaintext_password: Optional[str] = None    # base64; only when backend=plaintext
    uses: int = 0
    last_used_at: Optional[str] = None          # ISO 8601 UTC
    created_at: str = ""
    projects: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CredentialEntry":
        return cls(
            id=d["id"],
            url=d["url"],
            username=d["username"],
            label=d.get("label", ""),
            secret_backend=d.get("secret_backend", "keyring"),
            plaintext_password=d.get("plaintext_password"),
            uses=int(d.get("uses", 0)),
            last_used_at=d.get("last_used_at"),
            created_at=d.get("created_at", ""),
            projects=list(d.get("projects") or []),
            notes=d.get("notes", ""),
        )

    def score(self, now: Optional[float] = None) -> float:
        """Recency-weighted usage score.

        score = uses * 0.5 ** (days_since_last_used / 30)

        A brand-new never-used entry scores 0.
        A 30-day-old single-use entry scores 0.5.
        A heavily-used 6-month-stale entry decays toward irrelevance.
        """
        if self.uses <= 0 or not self.last_used_at:
            return 0.0
        try:
            t = datetime.fromisoformat(self.last_used_at.replace("Z", "+00:00"))
        except Exception:
            return float(self.uses)  # malformed timestamp: fall back to count
        if now is None:
            now = time.time()
        delta_s = max(0.0, now - t.timestamp())
        days = delta_s / 86400.0
        return self.uses * (0.5 ** (days / 30.0))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "x"


def _make_entry_id(url: str, username: str) -> str:
    """Build a stable, human-readable id from url+username.

    Form: <host-slug>-<user-slug>[-<short-uuid>] if collision.
    The caller (store) appends the disambiguator.
    """
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or url
    except Exception:
        host = url
    return f"{_slugify(host)}-{_slugify(username)}"


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class CredentialStore:
    """Read/write the credentials.yaml index.

    The store does NOT hold passwords directly when the backend is
    keyring; passwords flow through the SecretBackend you pass to
    `set_password()` / `get_password()`. The store only persists
    metadata.

    For the plaintext backend, the password (base64-encoded) sits
    inside this file under `plaintext_password`. The PlaintextBackend
    reaches into the store via `_read_plaintext_password` /
    `_write_plaintext_password`.
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = (root or user_data_dir()).resolve()
        self.path = self.root / INDEX_FILENAME

    # -- I/O --------------------------------------------------------------

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        # Tighten dir permissions on POSIX (best-effort).
        if os.name == "posix":
            try:
                os.chmod(self.root, 0o700)
            except OSError:
                pass

    def _load(self) -> dict:
        if not self.path.exists():
            return {"version": SCHEMA_VERSION, "entries": []}
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            # Corrupt file. Rather than wiping it, raise so the user can
            # rescue manually.
            raise RuntimeError(
                f"Credential index at {self.path} is corrupt YAML. "
                f"Move it aside and re-run.")
        if "entries" not in data:
            data["entries"] = []
        if data.get("version") != SCHEMA_VERSION:
            # Forward-only migrations would go here.
            data["version"] = SCHEMA_VERSION
        return data

    def _save(self, data: dict) -> None:
        self._ensure_root()
        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        atomic_write(self.path, text)
        # Tighten file permissions on POSIX.
        if os.name == "posix":
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass

    # -- Public API -------------------------------------------------------

    def list_entries(self) -> List[CredentialEntry]:
        data = self._load()
        return [CredentialEntry.from_dict(d) for d in data["entries"]]

    def get(self, entry_id: str) -> Optional[CredentialEntry]:
        for e in self.list_entries():
            if e.id == entry_id:
                return e
        return None

    def find(self, url: Optional[str] = None,
             username: Optional[str] = None) -> List[CredentialEntry]:
        out = []
        for e in self.list_entries():
            if url and e.url != url:
                continue
            if username and e.username != username:
                continue
            out.append(e)
        return out

    def add(self, url: str, username: str, *,
            label: str = "",
            secret_backend: str = "keyring",
            notes: str = "",
            project: Optional[str] = None) -> CredentialEntry:
        """Create a new metadata entry. Does NOT store a password —
        the caller must invoke a SecretBackend separately to do so.
        """
        if not url or not username:
            raise ValueError("url and username are required")

        data = self._load()
        existing_ids = {e["id"] for e in data["entries"]}
        base_id = _make_entry_id(url, username)
        entry_id = base_id
        if entry_id in existing_ids:
            # Disambiguate collision (same host + same username, but
            # different real entry — e.g. two saucedemo accounts named
            # 'admin' on different orgs).
            entry_id = f"{base_id}-{uuid.uuid4().hex[:6]}"

        entry = CredentialEntry(
            id=entry_id,
            url=url,
            username=username,
            label=label or f"{username}@{url}",
            secret_backend=secret_backend,
            plaintext_password=None,
            uses=0,
            last_used_at=None,
            created_at=_now_iso(),
            projects=[project] if project else [],
            notes=notes,
        )
        data["entries"].append(entry.to_dict())
        self._save(data)
        return entry

    def remove(self, entry_id: str) -> bool:
        data = self._load()
        before = len(data["entries"])
        data["entries"] = [e for e in data["entries"] if e["id"] != entry_id]
        if len(data["entries"]) == before:
            return False
        self._save(data)
        return True

    def bump_usage(self, entry_id: str,
                   project: Optional[str] = None) -> Optional[CredentialEntry]:
        """Increment uses + set last_used_at; record project ref."""
        data = self._load()
        found = None
        for d in data["entries"]:
            if d["id"] == entry_id:
                d["uses"] = int(d.get("uses", 0)) + 1
                d["last_used_at"] = _now_iso()
                if project:
                    projs = list(d.get("projects") or [])
                    if project not in projs:
                        projs.append(project)
                    d["projects"] = projs
                found = CredentialEntry.from_dict(d)
                break
        if found:
            self._save(data)
        return found

    def ranked(self, *, url: Optional[str] = None,
              now: Optional[float] = None) -> List[CredentialEntry]:
        """Return entries sorted by recency-weighted score, descending.

        If `url` is given, only entries for that URL.
        Ties broken by created_at desc (newer first).
        """
        entries = self.list_entries()
        if url:
            entries = [e for e in entries if e.url == url]
        entries.sort(
            key=lambda e: (e.score(now), e.created_at or ""),
            reverse=True,
        )
        return entries

    # -- Plaintext backend hooks (DO NOT call from outside backends.py) ---

    def _read_plaintext_password(self, entry_id: str) -> Optional[str]:
        e = self.get(entry_id)
        if not e:
            return None
        return e.plaintext_password

    def _write_plaintext_password(self, entry_id: str,
                                  encoded: Optional[str]) -> None:
        data = self._load()
        for d in data["entries"]:
            if d["id"] == entry_id:
                d["plaintext_password"] = encoded
                self._save(data)
                return
        raise KeyError(entry_id)


_DEFAULT_STORE: Optional[CredentialStore] = None


def get_default_store() -> CredentialStore:
    """Return a process-wide default store (lazy)."""
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = CredentialStore()
    return _DEFAULT_STORE
