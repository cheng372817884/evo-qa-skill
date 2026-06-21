"""
SystemBrain (YAML) ↔ OKF Document bridge.

This is the only module that knows about both worlds:
  - In-memory `evo_qa.core.system_brain.schemas` dataclasses
  - On-disk OKF `Document` (frontmatter + body)

It exists so that the rest of the OKF subsystem (export.py, import_.py)
operates on Documents only, and SystemBrain stays unaware of OKF.

Mapping rules (REQUIREMENTS-v1.4.md §20.2):
  - PageNode             → OKF type "Quirk" or "Flow" (heuristic by tags)
  - FieldObservation     → "Selector" or "Quirk" (by category)
  - Transition           → "Flow"
  - Question             → kept in-brain only (not exported — they're TODOs)
  - Contradiction        → kept in-brain only (negative evidence)

Confidence mapping:
  SystemBrain `Provenance.confidence` is float [0, 1]; we discretize:
    user_verified flag → "user-verified"
    confidence ≥ 0.7 AND ≥ 2 evidence runs → "multi-run"
    everything else                          → "single-run"

  §18.2 Gate 1 — single-run is filtered out by export.py before reaching
  the bundle; bridge.py only labels.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional

from .frontmatter import Document
from .types import (
    OkfType, PQ_PREFIX, OKF_VERSION,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _confidence_label(prov: dict) -> str:
    """Discretize a Provenance dict into our confidence ladder."""
    if prov.get("user_verified"):
        return "user-verified"
    score = float(prov.get("confidence", 0.0) or 0.0)
    evidence = prov.get("evidence") or []
    if score >= 0.7 and len(evidence) >= 2:
        return "multi-run"
    return "single-run"


def _provenance_to_pq(prov: dict, host: str) -> dict[str, Any]:
    """Translate a SystemBrain Provenance into pq_* frontmatter fields."""
    evidence = list(prov.get("evidence") or [])
    out = {
        "pq_confidence": _confidence_label(prov),
        "pq_origin": evidence,  # list of run-ids
        "pq_observation_count": len(evidence),
    }
    fs_run = prov.get("first_seen_run") or ""
    lv_run = prov.get("last_verified_run") or ""
    fs_at = prov.get("created_at") or ""
    lv_at = prov.get("updated_at") or ""
    if fs_at:
        out["pq_first_seen"] = fs_at
    if lv_at:
        out["pq_last_confirmed"] = lv_at
    if host:
        out["pq_host"] = host
    return out


# ---------------------------------------------------------------------------
# SystemBrain dataclass → OKF Document
# ---------------------------------------------------------------------------

def page_node_to_okf(page: Any, host: str = "") -> Document:
    """Convert a PageNode dataclass to an OKF Document.

    `page` may be a dataclass instance or a dict (already serialized).
    We accept both to make this importable without circular deps.
    """
    if hasattr(page, "__dataclass_fields__"):
        d = asdict(page)
    elif isinstance(page, dict):
        d = page
    else:
        raise TypeError(f"page_node_to_okf expects dataclass or dict, got {type(page)}")

    name = d.get("name") or d.get("id") or "unnamed"
    description = d.get("description") or ""
    tags = list(d.get("tags") or [])
    prov = d.get("provenance") or {}

    fm: dict[str, Any] = {
        "type": OkfType.QUIRK.value if "quirk" in tags else OkfType.FLOW.value,
        "title": name,
        "description": description,
        "tags": tags,
        "timestamp": prov.get("updated_at") or _now_iso(),
    }
    if d.get("url"):
        fm["resource"] = d["url"]
    fm.update(_provenance_to_pq(prov, host))

    body_lines: list[str] = []
    if d.get("notes"):
        body_lines.append(d["notes"])
    if d.get("known_selectors"):
        body_lines.append("\n# Known Selectors\n")
        for s in d["known_selectors"]:
            body_lines.append(f"- `{s}`")

    return Document(frontmatter=fm, body="\n".join(body_lines) + "\n",
                    has_frontmatter=True)


def field_observation_to_okf(obs: Any, host: str = "") -> Document:
    if hasattr(obs, "__dataclass_fields__"):
        d = asdict(obs)
    elif isinstance(obs, dict):
        d = obs
    else:
        raise TypeError(f"unexpected type {type(obs)}")

    field_name = d.get("field") or d.get("name") or "unnamed"
    selector = d.get("selector") or ""
    page_id = d.get("page_id") or ""
    is_required = d.get("required", False)
    prov = d.get("provenance") or {}

    fm: dict[str, Any] = {
        "type": OkfType.SELECTOR.value,
        "title": f"{field_name} on {page_id}" if page_id else field_name,
        "description": d.get("description") or f"Selector observation for `{field_name}`.",
        "tags": list(d.get("tags") or []) + (["required"] if is_required else []),
        "timestamp": prov.get("updated_at") or _now_iso(),
    }
    if selector:
        fm["resource"] = f"selector://{selector}"
    fm.update(_provenance_to_pq(prov, host))

    body_lines = [
        f"# Field: `{field_name}`",
        f"",
        f"- Selector: `{selector}`",
        f"- Page: `{page_id}`" if page_id else "",
        f"- Required: {is_required}",
    ]
    if d.get("notes"):
        body_lines.append("")
        body_lines.append(d["notes"])

    return Document(
        frontmatter=fm,
        body="\n".join(line for line in body_lines if line is not None) + "\n",
        has_frontmatter=True,
    )


def transition_to_okf(trans: Any, host: str = "") -> Document:
    if hasattr(trans, "__dataclass_fields__"):
        d = asdict(trans)
    elif isinstance(trans, dict):
        d = trans
    else:
        raise TypeError(f"unexpected type {type(trans)}")

    src = d.get("from_page") or d.get("source") or ""
    dst = d.get("to_page") or d.get("target") or ""
    trigger = d.get("trigger") or "unknown"
    prov = d.get("provenance") or {}

    fm: dict[str, Any] = {
        "type": OkfType.FLOW.value,
        "title": f"{src} → {dst} via {trigger}",
        "description": d.get("description") or f"Transition from `{src}` to `{dst}`.",
        "tags": ["transition"],
        "timestamp": prov.get("updated_at") or _now_iso(),
    }
    fm.update(_provenance_to_pq(prov, host))

    body = f"# Transition\n\nFrom **{src}** to **{dst}** triggered by `{trigger}`.\n"
    if d.get("notes"):
        body += "\n" + d["notes"] + "\n"

    return Document(frontmatter=fm, body=body, has_frontmatter=True)


# ---------------------------------------------------------------------------
# OKF Document → SystemBrain-compatible dict (for import staging)
# ---------------------------------------------------------------------------

def okf_to_staging_record(doc: Document, source_bundle: str) -> dict[str, Any]:
    """Convert an imported OKF Document into a staging record.

    Staging records DO NOT enter brain/system/ directly. They go to
    brain/_imported/<bundle>/<concept>.md AND a parallel `.staging.yaml`
    that captures the OKF metadata + import provenance.

    The user (or agent, with §18 Gate 1 + Gate 2 checks) decides whether
    to promote into the live brain.
    """
    fm = doc.frontmatter or {}

    # §20.3.B — demote external user-verified to multi-run.
    incoming_conf = fm.get("pq_confidence", "single-run")
    from .types import IMPORT_CONFIDENCE_DEMOTION
    safe_conf = IMPORT_CONFIDENCE_DEMOTION.get(incoming_conf, "single-run")

    return {
        "okf_type": fm.get("type", "Reference"),
        "title": fm.get("title", ""),
        "description": fm.get("description", ""),
        "tags": list(fm.get("tags") or []),
        "resource": fm.get("resource"),
        "timestamp": fm.get("timestamp"),
        "incoming_confidence": incoming_conf,
        "demoted_confidence": safe_conf,
        "incoming_origin": list(fm.get("pq_origin") or []),
        "import_origin": [f"imported-from:{source_bundle}"],
        "host": fm.get("pq_host", ""),
        "first_seen": fm.get("pq_first_seen"),
        "last_confirmed": fm.get("pq_last_confirmed"),
        "body": doc.body,
        "extra_frontmatter": {
            k: v for k, v in fm.items()
            if not k.startswith(PQ_PREFIX) and k not in {
                "type", "title", "description", "tags", "resource", "timestamp",
            }
        },
    }
