"""
OKF (Open Knowledge Format) v0.1 — Type definitions and constants.

Reference: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
License of upstream SPEC: Apache 2.0 (★[P6])

This module owns:
  - Type taxonomy (mapping our brain knowledge to OKF `type` field values)
  - Confidence enum (single-run / multi-run / user-verified)
  - Reserved filenames (per OKF SPEC §3.1)
  - Frontmatter field names (OKF standard + our pq_* extensions)

Design note:
  We never import this module's runtime types into SystemBrain itself.
  OKF is a *peripheral* import/export adapter — the in-memory brain
  representation stays SystemBrain's YAML schema (schemas.py).
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

OKF_VERSION = "0.1"

# ---------------------------------------------------------------------------
# OKF SPEC §3.1 — Reserved filenames at any directory level.
# These MUST NOT be used for concept documents.
RESERVED_FILENAMES = frozenset({"index.md", "log.md"})


# ---------------------------------------------------------------------------
# OKF SPEC §4.1 — `type` field is the only required frontmatter key.
# Values are NOT registered centrally. We pick descriptive, self-explanatory
# strings. Consumers MUST tolerate unknown types gracefully (§9).
#
# Mapping rule (REQUIREMENTS-v1.4.md §20.2.B):
#   brain content type             → OKF type
#   site UI quirk                  → "Quirk"
#   verified selector              → "Selector"
#   business flow                  → "Flow"
#   API endpoint contract obs      → "ApiContract"
#   deprecated/failed selector     → "DeprecatedSelector"
#   recurring non-bug issue        → "RecurringIssue"
#   cross-site heuristic           → "Heuristic"
#   reusable playbook              → "Playbook"

class OkfType(str, Enum):
    QUIRK = "Quirk"
    SELECTOR = "Selector"
    FLOW = "Flow"
    API_CONTRACT = "ApiContract"
    DEPRECATED_SELECTOR = "DeprecatedSelector"
    RECURRING_ISSUE = "RecurringIssue"
    HEURISTIC = "Heuristic"
    PLAYBOOK = "Playbook"
    REFERENCE = "Reference"  # OKF SPEC §4.1 example value


KNOWN_TYPES = frozenset(t.value for t in OkfType)


# ---------------------------------------------------------------------------
# REQUIREMENTS-v1.4.md §20.2.C — pq_* extension frontmatter fields.
# All custom fields use pq_ prefix to avoid collision with future OKF
# standard fields.
PQ_PREFIX = "pq_"

# Confidence ladder (§18.2 Gate 4)
Confidence = Literal["single-run", "multi-run", "user-verified"]
CONFIDENCE_VALUES = frozenset({"single-run", "multi-run", "user-verified"})

# §18.2 Gate 1 — single-run is NOT allowed in shared brain.
EXPORTABLE_CONFIDENCE = frozenset({"multi-run", "user-verified"})

# §20.3.B — external user-verified gets demoted to multi-run on import.
# Their "user-verified" is not ours.
IMPORT_CONFIDENCE_DEMOTION = {
    "user-verified": "multi-run",
    "multi-run": "multi-run",
    "single-run": "single-run",  # but blocked elsewhere
}


# ---------------------------------------------------------------------------
# Required + recommended OKF frontmatter keys (SPEC §4.1).
OKF_REQUIRED_FIELDS = frozenset({"type"})
OKF_RECOMMENDED_FIELDS = frozenset({
    "title", "description", "resource", "tags", "timestamp"
})

# Our extensions — none are required by OKF, but enforced by our importer
# (REQUIREMENTS-v1.4.md §18.2 Gate 2: `pq_origin` required for in-brain entries).
PQ_REQUIRED_FOR_BRAIN = frozenset({"pq_origin", "pq_confidence"})
PQ_RECOMMENDED_FIELDS = frozenset({
    "pq_first_seen", "pq_last_confirmed", "pq_observation_count",
})

# All recognized pq_* fields (for round-trip preservation).
PQ_KNOWN_FIELDS = PQ_REQUIRED_FOR_BRAIN | PQ_RECOMMENDED_FIELDS


# ---------------------------------------------------------------------------
# §20.3.D — Bundle README water-marking. Keys we always emit.
BUNDLE_README_KEYS = (
    "generated_by", "generated_at", "source_workspace_hash",
    "okf_version", "redaction_applied", "total_concepts",
    "confidence_distribution",
)
