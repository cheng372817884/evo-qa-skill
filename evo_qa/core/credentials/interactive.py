"""
Interactive layer: prompts that ask the user before doing anything.

Two consumption modes:

  1. Direct CLI (`python -m evo_qa.core.cli creds add`)
     -> uses `input()` / `getpass` for stdin.

  2. Agent-driven (Claude Code, Copaw, Cline...)
     -> the agent renders prompts in chat and calls the non-
        interactive helpers (`add_credential_noninteractive`,
        `select_credential_for_url`, etc.) once it has the
        answers.

Consent rules baked in:

  - Default answer to "save?" is always NO.
  - Plaintext backend is offered ONLY after keyring is shown
    to be unavailable, and the user must say YES to a warning.
  - Each new credential gets its own consent prompt; there is
    no global "always save" flag.
"""
from __future__ import annotations

import getpass
import sys
from typing import Optional, List

from .store import CredentialStore, CredentialEntry, get_default_store
from .backends import (
    SecretBackend, KeyringBackend, PlaintextBackend, NullBackend,
    detect_backend, BackendUnavailable,
)


# ---------------------------------------------------------------------------
# Tiny prompt helpers (only used in direct-CLI mode)
# ---------------------------------------------------------------------------

def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        v = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default
    return v or default


def _ask_yn(prompt: str, default: bool = False) -> bool:
    d = "y/N" if not default else "Y/n"
    try:
        v = input(f"{prompt} [{d}]: ").strip().lower()
    except EOFError:
        return default
    if not v:
        return default
    return v in ("y", "yes")


def _ask_password(prompt: str = "Password") -> str:
    try:
        return getpass.getpass(f"{prompt}: ")
    except (EOFError, KeyboardInterrupt):
        return ""


# ---------------------------------------------------------------------------
# Non-interactive primitives (agent-friendly, return dicts)
# ---------------------------------------------------------------------------

def add_credential_noninteractive(
    *,
    url: str,
    username: str,
    password: str,
    label: str = "",
    notes: str = "",
    project: Optional[str] = None,
    prefer_backend: str = "auto",      # "auto" | "keyring" | "plaintext_file"
    consented_plaintext: bool = False,  # required if backend resolves to plaintext
    store: Optional[CredentialStore] = None,
) -> dict:
    """Persist a new credential. Caller is responsible for consent.

    Returns {"ok": True/False, "entry_id": ..., "backend": ..., "msg": ...}.
    """
    store = store or get_default_store()

    # Pick backend
    backend: SecretBackend
    backend_name: str
    if prefer_backend == "plaintext_file":
        if not consented_plaintext:
            return {
                "ok": False,
                "msg": "Plaintext backend requires consented_plaintext=True. "
                       "Refusing to write a password to disk without explicit "
                       "consent.",
            }
        backend = PlaintextBackend(store)
        backend_name = "plaintext_file"
    elif prefer_backend == "keyring":
        try:
            backend = detect_backend(store, prefer="keyring")
            backend_name = "keyring"
        except BackendUnavailable as e:
            return {"ok": False, "msg": f"Keyring unavailable: {e}"}
    else:  # auto
        try:
            backend = detect_backend(store, prefer=None)
            backend_name = backend.name
        except BackendUnavailable:
            if not consented_plaintext:
                return {
                    "ok": False,
                    "msg": "No keyring backend available; plaintext fallback "
                           "requires consented_plaintext=True.",
                    "needs_consent": "plaintext_file",
                }
            backend = PlaintextBackend(store)
            backend_name = "plaintext_file"

    entry = store.add(
        url=url, username=username, label=label, notes=notes,
        project=project, secret_backend=backend_name,
    )
    try:
        backend.set(entry.id, password)
    except Exception as e:
        # roll back metadata so we don't leave an orphan
        store.remove(entry.id)
        return {"ok": False, "msg": f"Failed to write password: {e}"}

    return {
        "ok": True,
        "entry_id": entry.id,
        "backend": backend_name,
        "url": entry.url,
        "username": entry.username,
        "label": entry.label,
        "msg": f"Saved (backend: {backend_name}).",
    }


def get_password(entry_id: str,
                 store: Optional[CredentialStore] = None) -> Optional[str]:
    """Resolve a password for an entry. Picks the right backend by
    looking at the entry's metadata. Returns None if missing.
    """
    store = store or get_default_store()
    e = store.get(entry_id)
    if not e:
        return None
    if e.secret_backend == "keyring":
        try:
            kb = KeyringBackend()
            if kb.is_available():
                return kb.get(entry_id)
            return None
        except BackendUnavailable:
            return None
    if e.secret_backend == "plaintext_file":
        return PlaintextBackend(store).get(entry_id)
    return None


def remove_credential(entry_id: str,
                      store: Optional[CredentialStore] = None) -> dict:
    store = store or get_default_store()
    e = store.get(entry_id)
    if not e:
        return {"ok": False, "msg": f"No such entry: {entry_id}"}
    # try to clear from secret backend (best effort)
    try:
        if e.secret_backend == "keyring":
            kb = KeyringBackend()
            if kb.is_available():
                kb.delete(entry_id)
        elif e.secret_backend == "plaintext_file":
            PlaintextBackend(store).delete(entry_id)
    except Exception:
        pass
    store.remove(entry_id)
    return {"ok": True, "msg": f"Removed {entry_id}."}


def list_credentials(store: Optional[CredentialStore] = None,
                     url: Optional[str] = None) -> List[dict]:
    """Return ranked list as plain dicts (no passwords)."""
    store = store or get_default_store()
    out = []
    for e in store.ranked(url=url):
        out.append({
            "id": e.id,
            "url": e.url,
            "username": e.username,
            "label": e.label,
            "backend": e.secret_backend,
            "uses": e.uses,
            "last_used_at": e.last_used_at,
            "score": round(e.score(), 4),
            "projects": e.projects,
        })
    return out


def select_for_url(url: Optional[str] = None,
                   store: Optional[CredentialStore] = None,
                   top: int = 3) -> dict:
    """Return the top-N candidates plus a "default" pick.

    Used by `qa:run` / `qa:plan` to decide what to suggest:

        {"default": <id or null>,
         "candidates": [ {id,label,url,username,uses,score,...}, ... ],
         "is_empty": bool}
    """
    store = store or get_default_store()
    ranked = store.ranked(url=url)
    candidates = [
        {
            "id": e.id, "url": e.url, "username": e.username,
            "label": e.label, "uses": e.uses,
            "last_used_at": e.last_used_at,
            "score": round(e.score(), 4),
            "backend": e.secret_backend,
        }
        for e in ranked[:top]
    ]
    return {
        "default": candidates[0]["id"] if candidates else None,
        "candidates": candidates,
        "is_empty": len(ranked) == 0,
    }


# ---------------------------------------------------------------------------
# Interactive wizards (stdin/stdout, used by `creds add` etc.)
# ---------------------------------------------------------------------------

def wizard_add(*, store: Optional[CredentialStore] = None,
               default_url: Optional[str] = None,
               project: Optional[str] = None,
               human: bool = True) -> dict:
    """Walk the user through adding one credential.

    Steps:
      1. URL    (with default if provided)
      2. Username
      3. Password (getpass)
      4. Label   (optional)
      5. Backend choice: keyring (if available) or plaintext (with warning)
      6. Final consent: "Save? y/N"

    Returns the same dict shape as add_credential_noninteractive().
    """
    store = store or get_default_store()

    if human:
        print("")
        print("─── Add a credential ─────────────────────────────────")

    url = _ask("URL", default=default_url or "")
    if not url:
        return {"ok": False, "msg": "URL is required.", "cancelled": True}
    username = _ask("Username")
    if not username:
        return {"ok": False, "msg": "Username is required.", "cancelled": True}
    password = _ask_password()
    if not password:
        return {"ok": False, "msg": "Password cannot be empty.",
                "cancelled": True}
    label = _ask("Label (optional)", default=f"{username}@{url}")

    # Backend selection
    kb = KeyringBackend()
    keyring_ok = kb.is_available()

    backend_choice: str
    consented_plaintext = False
    if keyring_ok:
        if human:
            print("\n  Storage:")
            print("    1) OS keyring  (recommended — secure)")
            print("    2) Plaintext file  (less secure — readable by anyone "
                  "with file access)")
        choice = _ask("Choose 1 or 2", default="1")
        if choice == "2":
            if human:
                print("\n  ⚠  Plaintext storage means your password will be "
                      "written to:")
                print(f"     {store.path}")
                print("     base64-encoded. This is NOT encryption.")
            if not _ask_yn("  I understand the risk and want to use plaintext",
                           default=False):
                if human:
                    print("  → Falling back to keyring.")
                backend_choice = "keyring"
            else:
                backend_choice = "plaintext_file"
                consented_plaintext = True
        else:
            backend_choice = "keyring"
    else:
        if human:
            print("\n  ⚠  No OS keyring is available on this system "
                  "(headless Linux, missing `keyring` package, etc.).")
            print(f"     The only fallback is a plaintext file at:")
            print(f"     {store.path}")
            print("     Passwords would be base64-encoded but readable.")
        if not _ask_yn("  Save the password as plaintext anyway",
                       default=False):
            return {"ok": False, "cancelled": True,
                    "msg": "User declined plaintext fallback. Nothing saved."}
        backend_choice = "plaintext_file"
        consented_plaintext = True

    # Final consent — separate from backend choice on purpose.
    if human:
        print("")
        print(f"  About to save:  {label}")
        print(f"  URL:            {url}")
        print(f"  Username:       {username}")
        print(f"  Storage:        {backend_choice}")
    if not _ask_yn("  Save this credential", default=False):
        return {"ok": False, "cancelled": True,
                "msg": "User declined. Nothing saved."}

    res = add_credential_noninteractive(
        url=url, username=username, password=password,
        label=label, project=project,
        prefer_backend=backend_choice,
        consented_plaintext=consented_plaintext,
        store=store,
    )
    if human and res.get("ok"):
        print(f"  ✓ {res['msg']}")
    elif human:
        print(f"  ✗ {res.get('msg')}")
    return res


def wizard_first_run_if_empty(*,
                              store: Optional[CredentialStore] = None,
                              context_url: Optional[str] = None,
                              project: Optional[str] = None,
                              human: bool = True) -> dict:
    """If the store is empty, greet the user and offer to add one.

    Returns:
       {"created": bool, "skipped": bool, "entry_id": <id or null>}
    """
    store = store or get_default_store()
    if store.list_entries():
        return {"created": False, "skipped": True, "reason": "not_empty"}

    if human:
        print("")
        print("Welcome — this looks like your first time using credentials.")
        print("Evo QA can remember the URL + login for systems you")
        print("test against, so you don't have to re-type them every time.")
        print("")
        print("Nothing is saved unless you say so, and passwords go into")
        print("the OS keyring by default (not into a file).")
        print("")

    if not _ask_yn("Want to add one now", default=True):
        return {"created": False, "skipped": True, "reason": "user_declined"}

    res = wizard_add(store=store, default_url=context_url,
                    project=project, human=human)
    return {
        "created": bool(res.get("ok")),
        "skipped": not bool(res.get("ok")),
        "entry_id": res.get("entry_id"),
        "wizard_result": res,
    }


def wizard_pick_for_run(url: Optional[str] = None, *,
                        store: Optional[CredentialStore] = None,
                        project: Optional[str] = None,
                        human: bool = True) -> dict:
    """Pick a credential for a run.

    Behaviour:
      - If store empty -> offer first-run wizard.
      - If exactly 1 candidate -> return it directly.
      - If >1 candidate -> show top 3 with default = #1; user can
        accept (Enter), pick a number, or 'n' to add a new one.

    Returns: {"entry_id": ..., "url": ..., "username": ...,
              "password": ..., "source": "default"|"chosen"|"new"}
              or {"cancelled": True} if user bails.
    """
    store = store or get_default_store()
    sel = select_for_url(url=url, store=store)

    if sel["is_empty"]:
        wf = wizard_first_run_if_empty(store=store, context_url=url,
                                       project=project, human=human)
        if not wf.get("created"):
            return {"cancelled": True, "reason": "no_credentials"}
        eid = wf["entry_id"]
        e = store.get(eid)
        store.bump_usage(eid, project=project)
        return {
            "entry_id": eid, "url": e.url, "username": e.username,
            "password": get_password(eid, store=store),
            "source": "new",
        }

    cands = sel["candidates"]
    if len(cands) == 1 and not human:
        # Non-interactive single match → take it.
        c = cands[0]
        store.bump_usage(c["id"], project=project)
        return {
            "entry_id": c["id"], "url": c["url"], "username": c["username"],
            "password": get_password(c["id"], store=store),
            "source": "default",
        }

    if human:
        print("")
        print("Which credential should I use?")
        for i, c in enumerate(cands, 1):
            tag = "  ← default" if i == 1 else ""
            print(f"  {i}) {c['label']}  "
                  f"({c['username']} @ {c['url']}, "
                  f"used {c['uses']}x){tag}")
        print(f"  n) Add a new one")
        print(f"  q) Cancel")

    choice = _ask("Pick", default="1")
    if choice.lower() == "q":
        return {"cancelled": True}
    if choice.lower() == "n":
        res = wizard_add(store=store, default_url=url,
                         project=project, human=human)
        if not res.get("ok"):
            return {"cancelled": True, "reason": "add_failed"}
        eid = res["entry_id"]
        e = store.get(eid)
        store.bump_usage(eid, project=project)
        return {
            "entry_id": eid, "url": e.url, "username": e.username,
            "password": get_password(eid, store=store),
            "source": "new",
        }

    try:
        idx = int(choice) - 1
        c = cands[idx]
    except (ValueError, IndexError):
        return {"cancelled": True, "reason": "invalid_choice"}

    store.bump_usage(c["id"], project=project)
    return {
        "entry_id": c["id"], "url": c["url"], "username": c["username"],
        "password": get_password(c["id"], store=store),
        "source": "default" if idx == 0 else "chosen",
    }
