"""
Secret backends: where the actual password bytes live.

Three backends, in order of preference:

  1. KeyringBackend  -- OS-native secret store via the `keyring` lib.
                        Default. Pulls in zero plaintext on disk.
  2. PlaintextBackend -- AES-less, encoded-only fallback that writes
                         passwords into the credentials.yaml file.
                         REQUIRES explicit user consent. File is
                         chmod 600 on POSIX; ACL'd to current user
                         on Windows. NOT secure against a determined
                         attacker who already has FS access — it is
                         protection against shoulder-surfing only.
  3. NullBackend      -- in-memory only; for tests.

The store NEVER instantiates a backend on its own. The caller
(usually the interactive layer) chooses, after asking the user.
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from typing import Optional, Protocol


class BackendUnavailable(RuntimeError):
    """Raised when a backend cannot be used on this machine."""


class SecretBackend(Protocol):
    """Minimal interface for password storage."""

    name: str

    def is_available(self) -> bool: ...
    def set(self, entry_id: str, password: str) -> None: ...
    def get(self, entry_id: str) -> Optional[str]: ...
    def delete(self, entry_id: str) -> None: ...


# ---------------------------------------------------------------------------
# Keyring: OS-native (preferred)
# ---------------------------------------------------------------------------

class KeyringBackend:
    """Stores passwords in the OS keyring via the `keyring` library.

    Service name: "evo_qa". Usernames are entry IDs (stable,
    not the human-typed username) so multiple accounts on one URL
    don't collide.
    """

    name = "keyring"
    SERVICE = "evo_qa"

    def __init__(self) -> None:
        self._kr = None

    def _lazy(self):
        if self._kr is not None:
            return self._kr
        try:
            import keyring  # type: ignore
            import keyring.errors  # noqa: F401
        except ImportError as e:
            raise BackendUnavailable(
                "The `keyring` package is not installed. "
                "Install it with `pip install keyring` for OS-native "
                "password storage, or use the plaintext backend "
                "(less secure)."
            ) from e
        self._kr = keyring
        return keyring

    def is_available(self) -> bool:
        try:
            kr = self._lazy()
        except BackendUnavailable:
            return False
        # `keyring` always loads, but the *backend* it picked may be a
        # null backend on headless Linux. Probe by trying a write/read
        # of a sentinel.
        try:
            kr.set_password(self.SERVICE, "__probe__", "ok")
            v = kr.get_password(self.SERVICE, "__probe__")
            try:
                kr.delete_password(self.SERVICE, "__probe__")
            except Exception:
                pass
            return v == "ok"
        except Exception:
            return False

    def set(self, entry_id: str, password: str) -> None:
        kr = self._lazy()
        kr.set_password(self.SERVICE, entry_id, password)

    def get(self, entry_id: str) -> Optional[str]:
        kr = self._lazy()
        try:
            return kr.get_password(self.SERVICE, entry_id)
        except Exception:
            return None

    def delete(self, entry_id: str) -> None:
        kr = self._lazy()
        try:
            kr.delete_password(self.SERVICE, entry_id)
        except Exception:
            # idempotent delete
            pass


# ---------------------------------------------------------------------------
# Plaintext: requires explicit consent. Encoded (base64) only to avoid
# accidental shoulder-surf reading; this is NOT encryption.
# ---------------------------------------------------------------------------

class PlaintextBackend:
    """File-based fallback. Stores passwords inside the credentials
    yaml file under the entry's `plaintext_password` field, base64
    encoded.

    SECURITY: this protects against shoulder-surfing only. Any user
    or process that can read the file can recover the password.
    Use only when:
      - keyring is unavailable, AND
      - user has explicitly consented after seeing a warning.

    File permissions are tightened to 0600 on POSIX. On Windows we
    rely on the per-user APPDATA path (no extra ACL by default —
    documented as a known gap).
    """

    name = "plaintext_file"

    def __init__(self, store: "CredentialStore") -> None:  # noqa: F821
        self._store = store

    def is_available(self) -> bool:
        return True  # always — but consent gate is in the interactive layer

    def set(self, entry_id: str, password: str) -> None:
        encoded = base64.b64encode(password.encode("utf-8")).decode("ascii")
        self._store._write_plaintext_password(entry_id, encoded)

    def get(self, entry_id: str) -> Optional[str]:
        encoded = self._store._read_plaintext_password(entry_id)
        if encoded is None:
            return None
        try:
            return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
        except Exception:
            return None

    def delete(self, entry_id: str) -> None:
        self._store._write_plaintext_password(entry_id, None)


# ---------------------------------------------------------------------------
# Null: tests only
# ---------------------------------------------------------------------------

class NullBackend:
    """In-memory backend. For tests."""

    name = "null"

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def is_available(self) -> bool:
        return True

    def set(self, entry_id: str, password: str) -> None:
        self._data[entry_id] = password

    def get(self, entry_id: str) -> Optional[str]:
        return self._data.get(entry_id)

    def delete(self, entry_id: str) -> None:
        self._data.pop(entry_id, None)


# ---------------------------------------------------------------------------
# Auto-detect
# ---------------------------------------------------------------------------

def detect_backend(store: "CredentialStore",  # noqa: F821
                   prefer: Optional[str] = None) -> SecretBackend:
    """Pick a backend.

    `prefer` may be "keyring" or "plaintext_file". If keyring is
    requested but unavailable, raises BackendUnavailable so the
    caller can fall back interactively.
    """
    if prefer == "plaintext_file":
        return PlaintextBackend(store)
    if prefer == "keyring":
        kb = KeyringBackend()
        if not kb.is_available():
            raise BackendUnavailable(
                "Keyring is not available on this system. "
                "On headless Linux you may need to install "
                "`keyring`'s SecretService support, or use the "
                "plaintext backend.")
        return kb
    # Auto: keyring if usable, else raise (let caller ask user)
    kb = KeyringBackend()
    if kb.is_available():
        return kb
    raise BackendUnavailable(
        "No keyring backend is available on this system.")
