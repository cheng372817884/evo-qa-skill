"""
Login strategy — rule-based decider for charter.kind == 'login'.

Mental model:

  state machine roughly:

       NEED_USERNAME → NEED_PASSWORD → NEED_SUBMIT
                                          │
                  ┌─── try_wrong (once) ──┘
                  │
                  ▼
            OBSERVE_ERROR ─→ try_real ─→ OBSERVE_LANDING ─→ stop

  We use the snapshot's elements + step history to figure out which
  state we're in. No LLM.

Heuristics (in order of preference):

  - Find the first element with role='textbox' AND attrs.type='password'
    → that's the password input.
  - The closest sibling textbox above it (or the first textbox if there's
    no password element yet) → username input.
  - The submit button is a 'button' role with name containing
    "log in / login / sign in / submit" (case-insensitive),
    or any button right after the password field.

If we can't find a password input on the current snapshot, we navigate
to charter.target_url and try once more. If we still can't, we stop
with rationale "no login form detected".

Wrong creds attempt uses the literal pair ('wrongtest', 'wrongtest') —
chosen for being:
  - obviously not real (won't accidentally hit production)
  - safe ASCII
  - unlikely to look like SQL injection
"""
from __future__ import annotations

from typing import Optional

from ..schemas import (
    Charter, Action, ElementRef, Snapshot, ExplorationStep,
)
from . import register


WRONG_USERNAME = "wrongtest"
WRONG_PASSWORD = "wrongtest"

SUBMIT_KEYWORDS = ("log in", "login", "sign in", "signin", "submit", "登录")


def _find_password(snap: Snapshot) -> Optional[ElementRef]:
    # Prefer explicit type=password
    for e in snap.elements:
        if (e.attrs.get("type") == "password"
                or "password" in (e.name or "").lower()
                or "password" in (e.attrs.get("placeholder", "") or "").lower()
                or "password" in (e.attrs.get("id", "") or "").lower()):
            if e.role in ("textbox", "input", "searchbox"):
                return e
    return None


def _find_username(snap: Snapshot,
                   password_el: Optional[ElementRef]) -> Optional[ElementRef]:
    candidates = [e for e in snap.elements
                  if e.role in ("textbox", "input", "searchbox")
                  and e.attrs.get("type") not in ("password", "hidden", "file")]
    if not candidates:
        return None
    # Strong signal: explicit name like "user-name" / "username" / "email"
    for e in candidates:
        haystack = (
            (e.name or "")
            + " " + (e.attrs.get("placeholder", "") or "")
            + " " + (e.attrs.get("id", "") or "")
            + " " + (e.attrs.get("name", "") or "")
        ).lower()
        for kw in ("user", "email", "account", "login", "用户", "账号", "邮箱"):
            if kw in haystack:
                return e
    # Fallback: the textbox just before the password element
    if password_el is not None:
        try:
            i = snap.elements.index(password_el)
            for e in reversed(snap.elements[:i]):
                if e.role in ("textbox", "input", "searchbox"):
                    return e
        except ValueError:
            pass
    # Last resort: first textbox
    return candidates[0]


def _find_submit(snap: Snapshot,
                 password_el: Optional[ElementRef]) -> Optional[ElementRef]:
    # Prefer button whose name matches submit keywords
    for e in snap.elements:
        if e.role != "button":
            continue
        haystack = ((e.name or "") + " "
                    + (e.attrs.get("value", "") or "")
                    + " " + (e.attrs.get("id", "") or "")
                    + " " + (e.attrs.get("type", "") or "")).lower()
        for k in SUBMIT_KEYWORDS:
            if k in haystack:
                return e
    # Fallback: the button just after the password element
    if password_el is not None:
        try:
            i = snap.elements.index(password_el)
            for e in snap.elements[i + 1:]:
                if e.role == "button":
                    return e
        except ValueError:
            pass
    # Any button at all
    for e in snap.elements:
        if e.role == "button":
            return e
    return None


# ---------------------------------------------------------------------------

class LoginStrategy:
    name = "login"

    def initial_action(self, charter: Charter) -> Action:
        return Action(
            kind="navigate",
            value=charter.target_url,
            rationale="Open the target URL to begin login exploration.",
            expected="A page with a login form (username + password + submit).",
        )

    def is_satisfied(self, charter: Charter,
                     history: list[ExplorationStep]) -> bool:
        return any(s.notes and "LOGIN_SUCCESS" in s.notes for s in history)

    def next_action(self, charter: Charter,
                    current: Optional[Snapshot],
                    history: list[ExplorationStep]) -> Action:
        if current is None:
            return self.initial_action(charter)

        phase = self._phase(history)
        password = _find_password(current)
        username = _find_username(current, password)
        submit = _find_submit(current, password)

        if password is None or username is None or submit is None:
            return Action(
                kind="stop",
                rationale=(f"No login form detected on {current.url} "
                           f"(password={password is not None}, "
                           f"username={username is not None}, "
                           f"submit={submit is not None})."),
            )

        # Phase A: never tried the wrong creds yet.
        if phase == "before_wrong":
            return Action(
                kind="fill",
                target_ref=username.ref_id,
                value=WRONG_USERNAME,
                rationale="Trial run: fill username with a clearly invalid value "
                          "to capture the error path.",
                expected="No effect yet; password fill follows.",
            )
        if phase == "wrong_username_filled":
            return Action(
                kind="fill",
                target_ref=password.ref_id,
                value=WRONG_PASSWORD,
                rationale="Fill password with an obviously invalid value.",
                expected="No effect yet; submit follows.",
            )
        if phase == "wrong_password_filled":
            return Action(
                kind="click",
                target_ref=submit.ref_id,
                rationale="Submit invalid credentials to observe the error path.",
                expected="An error message; URL stays on login page.",
            )
        # Phase B: wrong creds tried. Now real creds, if available.
        if phase == "wrong_submitted":
            if not charter.credentials_id:
                return Action(
                    kind="stop",
                    rationale="Wrong-creds path captured; no real credentials "
                              "available, so we cannot continue to landing page.",
                )
            return Action(
                kind="fill",
                target_ref=username.ref_id,
                value="__CRED_USERNAME__",   # ExplorerLoop substitutes
                rationale="Fill username with stored credential.",
                expected="No effect yet; password follows.",
            )
        if phase == "real_username_filled":
            return Action(
                kind="fill",
                target_ref=password.ref_id,
                value="__CRED_PASSWORD__",
                rationale="Fill password with stored credential.",
                expected="No effect yet; submit follows.",
            )
        if phase == "real_password_filled":
            return Action(
                kind="click",
                target_ref=submit.ref_id,
                rationale="Submit real credentials.",
                expected="Navigation to a landing page; URL changes.",
            )
        # Phase C: real submitted. Capture landing page elements then stop.
        return Action(
            kind="stop",
            rationale="Login flow captured (wrong path + real path).",
        )

    # -- internal phase machine -----------------------------------------

    @staticmethod
    def _phase(history: list[ExplorationStep]) -> str:
        # Look only at successful, non-skipped fill/click actions.
        fills = [s for s in history
                 if s.action.kind == "fill" and not s.action.skipped]
        clicks = [s for s in history
                  if s.action.kind == "click" and not s.action.skipped]

        wrong_subs = sum(1 for c in clicks
                         if "wrong" in (c.action.rationale or "").lower()
                         or "invalid" in (c.action.rationale or "").lower())
        real_subs = sum(1 for c in clicks
                        if "real" in (c.action.rationale or "").lower()
                        or "stored credential" in (c.action.rationale or "").lower())

        # Use rationale (immutable) instead of value (mutated by
        # ExplorerLoop credential substitution).
        wrong_fills = sum(1 for f in fills
                          if "trial run" in (f.action.rationale or "").lower()
                          or "obviously invalid" in (f.action.rationale or "").lower())
        real_fills = sum(1 for f in fills
                         if "stored credential" in (f.action.rationale or "").lower())

        if wrong_fills == 0:
            return "before_wrong"
        if wrong_fills == 1 and wrong_subs == 0:
            return "wrong_username_filled"
        if wrong_fills >= 2 and wrong_subs == 0:
            return "wrong_password_filled"
        if wrong_subs >= 1 and real_fills == 0:
            return "wrong_submitted"
        if real_fills == 1 and real_subs == 0:
            return "real_username_filled"
        if real_fills >= 2 and real_subs == 0:
            return "real_password_filled"
        return "real_submitted"


register("login", LoginStrategy())
