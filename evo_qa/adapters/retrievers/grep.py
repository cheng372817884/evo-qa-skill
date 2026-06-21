"""Grep retriever — the simplest possible retrieval: keyword match + scoring.

Future iterations may upgrade to BM25 or vector search. The data contract
stays stable, so retrievers are hot-swappable.
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Optional

import yaml

from ...core.interfaces import Retriever
from ...core.schemas import Knowledge, KnowledgeSource


def _parse_md_with_frontmatter(path: Path) -> Optional[Knowledge]:
    """Read a .md file — supports YAML frontmatter."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    fm = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            try:
                fm = yaml.safe_load(text[4:end]) or {}
                body = text[end + 5:]
            except Exception:
                pass

    return Knowledge(
        id=fm.get("id", path.stem),
        type=fm.get("type", "reference"),
        scope=fm.get("scope", "project"),
        title=fm.get("title", path.stem),
        summary=fm.get("summary", body.split("\n")[0][:200] if body else ""),
        body=body,
        tags=fm.get("tags", []) or [],
        domains=fm.get("domains", ["all"]) or ["all"],
        priority=fm.get("priority", "medium"),
        source=KnowledgeSource(type=fm.get("source_type", "builtin"),
                               ref=fm.get("source_ref", str(path))),
        created_at=fm.get("created_at", ""),
        updated_at=fm.get("updated_at", ""),
    )


class GrepRetriever:
    name = "grep"

    def __init__(self):
        self._docs: list[tuple[Path, Knowledge]] = []

    def index(self, knowledge_dirs: list[Path]) -> None:
        self._docs = []
        for root in knowledge_dirs:
            if not root.exists():
                continue
            for p in root.rglob("*.md"):
                # Skip files starting with _ (index, README) AND any path
                # component starting with _ (e.g. _imported, _archive_*).
                if p.name.startswith("_") or p.name == "manifest.yml":
                    continue
                if any(part.startswith("_") for part in p.relative_to(root).parts):
                    continue
                k = _parse_md_with_frontmatter(p)
                if k:
                    self._docs.append((p, k))

    def search(
        self,
        query: str,
        scope: list[str] | None = None,
        tags: list[str] | None = None,
        top_k: int = 5,
    ) -> list[Knowledge]:
        if not self._docs:
            return []

        q_terms = [t.lower() for t in re.split(r"\W+", query) if len(t) > 1]
        scored: list[tuple[float, Knowledge]] = []

        for _path, k in self._docs:
            if scope and k.scope not in scope:
                continue
            if tags and not (set(tags) & set(k.tags)):
                continue

            blob = f"{k.title}\n{k.summary}\n{' '.join(k.tags)}\n{k.body}".lower()
            score = 0.0
            for t in q_terms:
                if t in blob:
                    # Title hits get a higher weight
                    score += 3.0 if t in k.title.lower() else 1.0
                    # Tag hits get a weighted bonus
                    if t in " ".join(k.tags).lower():
                        score += 1.5
            # Priority bonus
            score *= {"high": 1.3, "medium": 1.0, "low": 0.8}.get(k.priority, 1.0)

            if score > 0:
                scored.append((score, k))

        scored.sort(key=lambda x: -x[0])
        return [k for _s, k in scored[:top_k]]


__all__ = ["GrepRetriever"]
