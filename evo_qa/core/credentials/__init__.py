"""
core.credentials — user-level credential store for Evo QA.

Why user-level (not workspace-level):
  Credentials are tied to humans + target systems, not to projects.
  The same QA engineer testing 3 projects against the same
  dev env should not re-enter the password three times.

Design constraints (DO NOT VIOLATE):

  1. Passwords NEVER touch:
     - brain entries
     - run records
     - reports (HTML or otherwise)
     - logs
     - plan / change packages
     - generated pytest code (which uses ${creds.<id>.password} placeholders)

  2. Default storage is the OS keyring (macOS Keychain / Windows
     Credential Manager / Linux Secret Service via the `keyring` lib).

  3. Plaintext fallback exists ONLY when:
     - keyring backend is unavailable AND
     - the user has explicitly consented in an interactive prompt

  4. Saving ANY credential requires explicit user consent. The default
     answer is always "no save".

  5. The metadata index (~/.evo_qa/credentials.yaml) contains
     URLs, usernames, labels, and usage stats — but never passwords,
     unless the plaintext backend was explicitly chosen.

Public surface:

    from evo_qa.core.credentials import (
        CredentialStore, CredentialEntry, get_default_store,
    )
"""
from __future__ import annotations

from .store import (
    CredentialStore,
    CredentialEntry,
    get_default_store,
    user_data_dir,
)
from .backends import (
    SecretBackend,
    KeyringBackend,
    PlaintextBackend,
    NullBackend,
    detect_backend,
    BackendUnavailable,
)

__all__ = [
    "CredentialStore",
    "CredentialEntry",
    "get_default_store",
    "user_data_dir",
    "SecretBackend",
    "KeyringBackend",
    "PlaintextBackend",
    "NullBackend",
    "detect_backend",
    "BackendUnavailable",
]
