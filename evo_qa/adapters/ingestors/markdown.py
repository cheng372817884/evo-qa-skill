"""Ingestor for Markdown and plain-text materials."""

from __future__ import annotations
from pathlib import Path

from ...core.interfaces import Ingestor, Source
from ...core.schemas import Knowledge, KnowledgeSource


SUPPORTED_EXTS = {".md", ".markdown", ".txt", ".rst"}


class MarkdownIngestor:
    name = "markdown"

    def can_handle(self, source: Source) -> bool:
        if source.kind == "text":
            return True
        if source.kind == "file":
            return Path(source.location).suffix.lower() in SUPPORTED_EXTS
        return False

    def ingest(self, source: Source) -> list[Knowledge]:
        if source.kind == "text":
            content = source.location
            ref = source.meta.get("ref", "inline-text")
            title = source.meta.get("title", "Inline note")
        else:
            p = Path(source.location)
            content = p.read_text(encoding="utf-8", errors="ignore")
            ref = str(p)
            title = p.stem.replace("-", " ").replace("_", " ").title()

        # One document = one reference knowledge entry. Future versions may split by section.
        slug = title.lower().replace(" ", "-")[:50]
        return [Knowledge(
            id=f"reference-{slug}",
            type="reference",
            scope="project",
            title=title,
            summary=content.split("\n")[0][:200] if content else title,
            body=content,
            tags=source.meta.get("tags", []),
            source=KnowledgeSource(type="ingest", ref=ref),
            created_at=Knowledge.now(),
            updated_at=Knowledge.now(),
        )]


__all__ = ["MarkdownIngestor"]
