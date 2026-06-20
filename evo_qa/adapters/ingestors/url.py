"""URL ingestor — turn a URL into a knowledge entry.

Default behavior: open with Playwright, grab title + main text, persist
as a `reference` knowledge entry. More sophisticated strategies (Reader
API, sitemap traversal, etc.) can be plugged in by replacing this adapter.
"""

from __future__ import annotations

from ...core.interfaces import Ingestor, Source
from ...core.schemas import Knowledge, KnowledgeSource


class URLIngestor:
    name = "url"

    def can_handle(self, source: Source) -> bool:
        return source.kind == "url"

    def ingest(self, source: Source) -> list[Knowledge]:
        # Lazy mode: record the URL as a reference without fetching.
        # We avoid launching the browser at ingest time; the plan stage
        # will visit the URL when it actually needs the page contents.
        url = source.location
        return [Knowledge(
            id=f"reference-url-{abs(hash(url)) % 10000}",
            type="reference",
            scope="project",
            title=f"URL: {url}",
            summary=f"External URL referenced by user: {url}",
            body=f"# {url}\n\n_To be visited during planning phase._\n",
            tags=source.meta.get("tags", ["url"]),
            source=KnowledgeSource(type="ingest", ref=url),
            created_at=Knowledge.now(),
            updated_at=Knowledge.now(),
        )]


__all__ = ["URLIngestor"]
