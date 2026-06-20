"""
evo_qa.core.okf — Open Knowledge Format (OKF) v0.1 adapter.

OKF is evo-qa's interchange format for cross-user / cross-org
knowledge sharing. We adopt the Google open standard as defined in
https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
(★[P6], Apache 2.0).

Design philosophy: OKF is a peripheral *adapter*, not a brain rewrite.
The in-memory brain stays SystemBrain (YAML, schemas.py). OKF is the
shape that knowledge takes when leaving or entering this workspace.

Module map
----------
- types       : OKF type taxonomy, confidence enum, reserved filenames
- frontmatter : YAML frontmatter parse/serialize (no python-frontmatter dep)
- redact      : mandatory redaction pipeline (always-on, audit-logged)
- bridge      : SystemBrain dataclasses ↔ OKF Document
- bundle      : bundle layout, index.md / log.md / README generation
- export      : `pq brain export --format okf`
- import_     : `pq brain import okf-bundle`

Trust boundary
--------------
Imports go to `brain/_imported/<bundle>/` staging — never directly to
brain/sites/. Promotion requires §18.2's 4 gates. Their user-verified
is not ours; we auto-demote on import.

Reference
---------
- REQUIREMENTS-v1.4.md §20 (full RFC)
- REQUIREMENTS-v1.2.md §18 (brain promotion gates)
- ATTRIBUTION.md ★[P6] (upstream credit)
"""
from .types import (
    OKF_VERSION,
    OkfType,
    Confidence,
    EXPORTABLE_CONFIDENCE,
    IMPORT_CONFIDENCE_DEMOTION,
)
from .frontmatter import Document, parse, serialize, parse_file, write_file
from .redact import (
    RedactionEvent,
    RedactionResult,
    redact_text,
    redact_document,
    load_custom_rules,
)
from .export import export_to_bundle, discover_concepts
from .import_ import import_bundle, validate_bundle

__all__ = [
    "OKF_VERSION",
    "OkfType",
    "Confidence",
    "EXPORTABLE_CONFIDENCE",
    "IMPORT_CONFIDENCE_DEMOTION",
    "Document",
    "parse",
    "serialize",
    "parse_file",
    "write_file",
    "RedactionEvent",
    "RedactionResult",
    "redact_text",
    "redact_document",
    "load_custom_rules",
    "export_to_bundle",
    "discover_concepts",
    "import_bundle",
    "validate_bundle",
]
