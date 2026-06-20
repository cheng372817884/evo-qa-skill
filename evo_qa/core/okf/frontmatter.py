"""
OKF frontmatter parser/serializer.

Markdown files in OKF format begin with a YAML frontmatter block delimited
by `---` on its own line at file start, with a closing `---` on its own
line. Body follows.

We deliberately do NOT depend on `python-frontmatter`. PyYAML is already
a dependency of evo-qa; rolling our own is ~50 lines and avoids
yet another transitive dep (Black-Box Scripts principle, v1.1.0).

Conformance scope:
  - Parse: any UTF-8 markdown file with optional frontmatter
  - Serialize: produce frontmatter that round-trips via `parse(serialize(x)) == x`
  - Preserve: unknown keys are preserved on round-trip (OKF SPEC §4.1, §9)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml

# A frontmatter block is `^---\n` ... `\n---\n` at the start of file.
_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z",
    re.DOTALL,
)


@dataclass
class Document:
    """A parsed OKF concept document.

    Attributes
    ----------
    frontmatter : dict
        Parsed YAML mapping, or empty dict if absent. Unknown keys preserved.
    body : str
        Markdown content after the frontmatter block (no leading newline).
    has_frontmatter : bool
        True if the source file actually had a frontmatter block.
    """
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    has_frontmatter: bool = False

    def get_type(self) -> Optional[str]:
        """Return the OKF `type` value, or None if missing."""
        v = self.frontmatter.get("type")
        return v if isinstance(v, str) and v else None

    def is_okf_conformant(self) -> bool:
        """OKF SPEC §9 — minimum conformance for a non-reserved concept doc."""
        return self.has_frontmatter and bool(self.get_type())


def parse(text: str) -> Document:
    """Parse markdown text into a Document.

    Empty / no-frontmatter input yields a Document with `has_frontmatter=False`
    and the entire text as `body`. We never raise on missing frontmatter
    (OKF SPEC §9 — consumers MUST tolerate non-conformant inputs).
    """
    if not text:
        return Document(frontmatter={}, body="", has_frontmatter=False)

    m = _FRONTMATTER_RE.match(text)
    if not m:
        return Document(frontmatter={}, body=text, has_frontmatter=False)

    fm_yaml, body = m.group(1), m.group(2)
    try:
        loaded = yaml.safe_load(fm_yaml) or {}
    except yaml.YAMLError:
        # Malformed frontmatter: treat as no-frontmatter, keep text as body.
        # We don't raise — caller can detect via `has_frontmatter`.
        return Document(frontmatter={}, body=text, has_frontmatter=False)

    if not isinstance(loaded, dict):
        # Frontmatter was a list/scalar — also treat as malformed.
        return Document(frontmatter={}, body=text, has_frontmatter=False)

    return Document(frontmatter=loaded, body=body, has_frontmatter=True)


def serialize(doc: Document) -> str:
    """Serialize a Document back to markdown text.

    YAML output is canonicalized:
      - sort_keys=False (preserve declared order if dict is insertion-ordered)
      - default_flow_style=False (always block style for readability)
      - allow_unicode=True (don't escape e.g. Chinese, em-dashes)
    """
    if not doc.frontmatter:
        return doc.body

    fm_text = yaml.safe_dump(
        doc.frontmatter,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    ).rstrip()

    return f"---\n{fm_text}\n---\n{doc.body}"


def parse_file(path) -> Document:
    """Convenience: read a file and parse its frontmatter."""
    from pathlib import Path
    p = Path(path)
    return parse(p.read_text(encoding="utf-8"))


def write_file(path, doc: Document) -> None:
    """Convenience: serialize a Document and write to disk (UTF-8)."""
    from pathlib import Path
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(serialize(doc), encoding="utf-8")
