"""
Guards — silently block dangerous actions.

Per user directive: prefer silent skip over confirmation prompts.
"Asking the user every time defeats automation."

Three guards, applied in order before any Action is executed:

  1. BlacklistGuard  — element text contains destructive keywords
  2. OriginGuard     — action would navigate outside the project URL's
                       origin
  3. AlreadyDoneGuard — same (selector, action) pair was attempted
                        in this exploration; prevent loops

Each guard returns Decision(allow: bool, reason: str). On block, the
ExplorerLoop logs the skip into the step record and tries to continue
with a different element. No prompt, no question.

Convention: BlacklistGuard is intentionally aggressive — false-positives
(refusing benign clicks) are acceptable; false-negatives (allowing a
destructive click) are not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import urlparse

from .schemas import Action, ElementRef, Snapshot


# ---------------------------------------------------------------------------
# Blacklist keywords. Case-insensitive substring match against:
#   - the element's accessible name
#   - its visible text
#   - its href / id / class attribute values
#
# This list is deliberately broad. v1.0.5 will let projects supplement
# it via brain/exploration/blacklist.yaml.
# ---------------------------------------------------------------------------

DESTRUCTIVE_KEYWORDS = (
    # English
    "delete", "remove", "destroy", "drop", "clear all",
    "wipe", "purge", "trash", "discard",
    "cancel subscription", "cancel account", "close account",
    "deactivate", "deactivat",
    "terminate", "uninstall", "unsubscribe",
    "unlink", "disconnect",
    "reset password", "forgot password",  # don't accidentally trigger flows
    "buy now", "place order", "pay", "checkout",
    "transfer", "withdraw", "send money",
    "publish", "submit for approval",
    "logout", "sign out",  # blocked here; ExplorerLoop opts in explicitly
    # Chinese
    "删除", "注销", "退订", "取消订阅", "解除", "永久删除", "停用",
    "退款", "提现", "转账", "立即购买", "立即支付", "确认支付",
    "退出登录", "退出账号",
    # SQL-like / code injection-y
    "drop table", "truncate", "exec ", "system(",
)


@dataclass
class GuardDecision:
    allow: bool
    reason: str = ""
    guard: str = ""


class BlacklistGuard:
    """Block actions that would touch destructive elements."""

    name = "blacklist"

    def __init__(self, extra_keywords: Optional[list[str]] = None) -> None:
        kw = list(DESTRUCTIVE_KEYWORDS)
        if extra_keywords:
            kw.extend(extra_keywords)
        self._kw = [k.lower() for k in kw]

    def check(self, action: Action,
              element: Optional[ElementRef]) -> GuardDecision:
        if action.kind not in ("click", "fill", "press", "navigate"):
            return GuardDecision(True, guard=self.name)
        if element is None and action.kind == "navigate":
            # navigate without an element ref: check the value (URL)
            for k in self._kw:
                if k in action.value.lower():
                    return GuardDecision(False,
                                         reason=f"navigate URL contains '{k}'",
                                         guard=self.name)
            return GuardDecision(True, guard=self.name)
        if element is None:
            return GuardDecision(True, guard=self.name)

        haystack = " ".join([
            element.name or "", element.text or "",
            element.attrs.get("id", ""),
            element.attrs.get("class", ""),
            element.attrs.get("href", ""),
            element.attrs.get("aria-label", ""),
        ]).lower()
        for k in self._kw:
            if k in haystack:
                return GuardDecision(
                    False,
                    reason=f"element matches blacklisted keyword '{k}'",
                    guard=self.name,
                )
        return GuardDecision(True, guard=self.name)


class OriginGuard:
    """Block navigations that would leave the project's origin."""

    name = "origin"

    def __init__(self, allowed_origins: Iterable[str]) -> None:
        self._origins = set()
        for u in allowed_origins:
            o = self._origin_of(u)
            if o:
                self._origins.add(o)

    @staticmethod
    def _origin_of(url: str) -> Optional[str]:
        try:
            p = urlparse(url)
            if not p.scheme or not p.netloc:
                return None
            return f"{p.scheme}://{p.netloc}".lower()
        except Exception:
            return None

    def check(self, action: Action,
              element: Optional[ElementRef]) -> GuardDecision:
        target_url = ""
        if action.kind == "navigate":
            target_url = action.value
        elif action.kind == "click" and element is not None:
            target_url = element.attrs.get("href", "")

        if not target_url:
            return GuardDecision(True, guard=self.name)

        # Relative URLs are same-origin.
        if target_url.startswith(("/", "?", "#")):
            return GuardDecision(True, guard=self.name)

        origin = self._origin_of(target_url)
        if origin is None:
            return GuardDecision(True, guard=self.name)
        if origin not in self._origins:
            return GuardDecision(
                False,
                reason=f"target origin {origin} not in allowlist "
                       f"{sorted(self._origins)}",
                guard=self.name,
            )
        return GuardDecision(True, guard=self.name)


class AlreadyDoneGuard:
    """Prevent loops: same (kind, target_ref/value) already attempted."""

    name = "already_done"

    def __init__(self) -> None:
        self._seen: set[tuple] = set()

    def record(self, action: Action) -> None:
        self._seen.add(self._key(action))

    def check(self, action: Action,
              element: Optional[ElementRef]) -> GuardDecision:
        if action.kind in ("wait", "stop"):
            return GuardDecision(True, guard=self.name)
        if self._key(action) in self._seen:
            return GuardDecision(
                False,
                reason="action already attempted in this exploration",
                guard=self.name,
            )
        return GuardDecision(True, guard=self.name)

    @staticmethod
    def _key(action: Action) -> tuple:
        # Rationale is included so that "click Login (wrong creds)" and
        # "click Login (real creds)" are treated as distinct intents.
        # Without this, the second submit gets skipped as a duplicate.
        return (action.kind, action.target_ref or "",
                action.value or "", (action.rationale or "")[:60])


def evaluate_all(action: Action,
                 element: Optional[ElementRef],
                 guards: list) -> GuardDecision:
    """Run guards in order; first block wins."""
    for g in guards:
        d = g.check(action, element)
        if not d.allow:
            return d
    return GuardDecision(True, reason="ok")


__all__ = [
    "BlacklistGuard", "OriginGuard", "AlreadyDoneGuard",
    "GuardDecision", "evaluate_all", "DESTRUCTIVE_KEYWORDS",
]
