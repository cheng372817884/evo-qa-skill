"""CTRF v1.0 data layer.

Evo QA v1.1 separates the report into two layers:

- Data layer: `result.ctrf.json` — strict CTRF v1.0 schema. Source of
  truth, tool-portable, machine-validated.
- View layer: `report.html` — styled, self-contained HTML report.
  Rendered FROM the CTRF JSON. Replaceable.

This package owns the data layer.
"""
from .ctrf import (
    build_ctrf,
    validate_ctrf,
    CtrfValidationError,
    CTRF_SPEC_VERSION,
    SKILL_GENERATED_BY,
)
from .writer import write_ctrf_for_run
from . import portable_export

__all__ = [
    "build_ctrf",
    "validate_ctrf",
    "CtrfValidationError",
    "CTRF_SPEC_VERSION",
    "SKILL_GENERATED_BY",
    "write_ctrf_for_run",
    "portable_export",
]
