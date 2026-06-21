"""
OKF export redaction pipeline (§20.3.C).

Methodology borrowed from ConversationLearner SKILL.md §3 REDACTION RULES
(★[P6] GoogleCloudPlatform/knowledge-catalog, Apache 2.0).
We re-implement; we do not import.

Design constraints
------------------
1. Mandatory. There is NO `--no-redact` option. To export raw, users must
   bypass this skill entirely (e.g. `cp -r brain/ outside/`). That's
   their workspace, their responsibility.
2. Heuristic, not deterministic. We surface high-confidence patterns and
   FLAG ambiguous ones for human review. We never silently pass-through
   anything that looks like an identifier we don't recognize.
3. Idempotent. Running redact twice yields the same output as once.
4. Auditable. Returns a list of (original, replacement, reason) tuples
   so the bundle README can record what was scrubbed.

Order of operations matters:
  1. URL query params containing token/key/secret BEFORE generic email
     match (a token can look email-shaped).
  2. Email regex.
  3. Long-digit identifiers (≥8 digits).
  4. Custom user rules (`brain/.export-rules.yaml`) applied last so they
     can target whatever the built-ins miss.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class RedactionEvent:
    """One redaction operation, recorded for the bundle audit log."""
    pattern: str           # e.g. "email", "url_token", "long_digit"
    original: str
    replacement: str
    location_hint: str = ""  # e.g. "frontmatter:resource", "body:line-42"


@dataclass
class RedactionResult:
    """Output of a single redact() pass over a string."""
    text: str
    events: list[RedactionEvent] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Built-in patterns. Each is a (compiled_regex, pattern_name, replacement_fn).
# replacement_fn receives the match object and returns the substitution.

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# URL with sensitive query keys: token=, key=, secret=, password=, api_key=,
# access_token=, refresh_token=, sig=, signature=
_URL_SENSITIVE_QUERY_RE = re.compile(
    r"(?P<key>(?:token|key|secret|password|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|sig|signature)\s*=\s*)"
    r"(?P<val>[A-Za-z0-9._\-+/=%]{4,})",
    re.IGNORECASE,
)

# Long digit sequences (≥8) — likely IDs, account numbers, phone, SSN.
# We're conservative: only standalone runs, not embedded in words.
_LONG_DIGITS_RE = re.compile(r"(?<!\w)\d{8,}(?!\w)")

# JWT-like tokens (3 base64 segments separated by dots).
_JWT_RE = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)

# AWS access key pattern (AKIA + 16 alphanumerics).
_AWS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")

# Bearer token in Authorization-style strings.
_BEARER_RE = re.compile(
    r"(?P<prefix>Bearer\s+)(?P<val>[A-Za-z0-9._\-+/=]{8,})"
)


def _redact_with(
    text: str,
    pattern: re.Pattern,
    name: str,
    replacement: str,
    full_match_substitute: bool = True,
    location_hint: str = "",
) -> RedactionResult:
    """Generic helper: substitute regex matches with `replacement`,
    log each as a RedactionEvent."""
    events: list[RedactionEvent] = []

    def _sub(m: re.Match) -> str:
        if full_match_substitute:
            original = m.group(0)
            events.append(RedactionEvent(
                pattern=name, original=original, replacement=replacement,
                location_hint=location_hint,
            ))
            return replacement
        # Capture-group preserving form: keep the named "key" or "prefix",
        # only redact the named "val".
        if "val" in m.groupdict():
            prefix = m.group("key") if "key" in m.groupdict() else m.group("prefix")
            val = m.group("val")
            events.append(RedactionEvent(
                pattern=name, original=val, replacement=replacement,
                location_hint=location_hint,
            ))
            return f"{prefix}{replacement}"
        return m.group(0)

    new_text = pattern.sub(_sub, text)
    return RedactionResult(text=new_text, events=events)


def redact_text(
    text: str,
    custom_rules: Optional[list[dict]] = None,
    location_hint: str = "",
) -> RedactionResult:
    """Apply the full redaction pipeline to a string.

    Parameters
    ----------
    text : str
        Input text (markdown body or frontmatter value).
    custom_rules : list[dict] | None
        Each rule is {"pattern": <regex>, "replacement": <str>, "name": <str>}.
        Loaded from `brain/.export-rules.yaml` typically.
    location_hint : str
        Free-form hint for audit log (e.g. "body:quirks/foo.md", "frontmatter").

    Returns
    -------
    RedactionResult
        Scrubbed text plus list of redaction events.
    """
    all_events: list[RedactionEvent] = []
    cur = text

    # 1. AWS keys (highest confidence, do first — they're never legitimate in docs)
    r = _redact_with(cur, _AWS_KEY_RE, "aws_access_key", "[REDACTED_AWS_KEY]",
                    location_hint=location_hint)
    cur, evs = r.text, r.events
    all_events.extend(evs)

    # 2. JWT tokens
    r = _redact_with(cur, _JWT_RE, "jwt", "[REDACTED_JWT]",
                    location_hint=location_hint)
    cur, evs = r.text, r.events
    all_events.extend(evs)

    # 3. Bearer tokens (preserve "Bearer " prefix for context)
    r = _redact_with(cur, _BEARER_RE, "bearer_token", "[REDACTED_BEARER]",
                    full_match_substitute=False, location_hint=location_hint)
    cur, evs = r.text, r.events
    all_events.extend(evs)

    # 4. URL query params with sensitive keys (preserve "token=" etc.)
    r = _redact_with(cur, _URL_SENSITIVE_QUERY_RE, "url_secret_param",
                    "[REDACTED]", full_match_substitute=False,
                    location_hint=location_hint)
    cur, evs = r.text, r.events
    all_events.extend(evs)

    # 5. Email addresses
    r = _redact_with(cur, _EMAIL_RE, "email", "[REDACTED_EMAIL]",
                    location_hint=location_hint)
    cur, evs = r.text, r.events
    all_events.extend(evs)

    # 6. Long digit sequences (8+ digits) — conservative, may yield false
    # positives (e.g. timestamps). Users can opt into exception via custom rules.
    r = _redact_with(cur, _LONG_DIGITS_RE, "long_digit", "[REDACTED_ID]",
                    location_hint=location_hint)
    cur, evs = r.text, r.events
    all_events.extend(evs)

    # 7. Custom user rules
    if custom_rules:
        for rule in custom_rules:
            try:
                pat = re.compile(rule["pattern"])
                name = rule.get("name", "custom")
                replacement = rule.get("replacement", "[REDACTED]")
                r = _redact_with(cur, pat, name, replacement,
                                location_hint=location_hint)
                cur, evs = r.text, r.events
                all_events.extend(evs)
            except (KeyError, re.error):
                # Bad rule — skip; do NOT fail the whole export.
                continue

    return RedactionResult(text=cur, events=all_events)


def load_custom_rules(workspace_root: Path) -> list[dict]:
    """Load `brain/.export-rules.yaml` if present.

    Schema:
        rules:
          - name: company_internal_id
            pattern: 'ACME-[0-9]{5,}'
            replacement: '[REDACTED_INTERNAL_ID]'
          - name: ...

    Missing file = no custom rules (empty list). Malformed file = empty
    list + a single warning event (caller can surface).
    """
    rules_file = Path(workspace_root) / "brain" / ".export-rules.yaml"
    if not rules_file.exists():
        return []
    try:
        data = yaml.safe_load(rules_file.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return []
    rules = data.get("rules", [])
    if not isinstance(rules, list):
        return []
    return [r for r in rules if isinstance(r, dict)]


def redact_document(doc, custom_rules: Optional[list[dict]] = None) -> tuple:
    """Redact both frontmatter values (string-typed) and body of a Document.

    Returns
    -------
    (Document, list[RedactionEvent])
        New document with redacted content, and full audit log.
    """
    from copy import deepcopy
    from .frontmatter import Document

    new_fm = deepcopy(doc.frontmatter) if doc.frontmatter else {}
    all_events: list[RedactionEvent] = []

    # Walk frontmatter, redacting string values. Don't touch keys; don't
    # touch list/dict structure beyond strings inside.
    def _walk(node, hint: str):
        if isinstance(node, str):
            r = redact_text(node, custom_rules, location_hint=hint)
            all_events.extend(r.events)
            return r.text
        if isinstance(node, list):
            return [_walk(v, hint) for v in node]
        if isinstance(node, dict):
            return {k: _walk(v, f"{hint}:{k}") for k, v in node.items()}
        return node

    new_fm = {k: _walk(v, f"frontmatter:{k}") for k, v in new_fm.items()}

    # Body
    r = redact_text(doc.body, custom_rules, location_hint="body")
    all_events.extend(r.events)
    new_body = r.text

    new_doc = Document(
        frontmatter=new_fm, body=new_body, has_frontmatter=doc.has_frontmatter,
    )
    return new_doc, all_events
