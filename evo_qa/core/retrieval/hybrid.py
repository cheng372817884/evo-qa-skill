"""Hybrid retriever — substring + BM25.

Below `BM25_THRESHOLD` entries: substring scoring only (cheap, exact).
At/above the threshold: BM25 is added and the two scores blend.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from .._vendor.rank_bm25 import BM25Okapi


# Above this many indexed entries, substring quality starts to collapse;
# bring BM25 online.
BM25_THRESHOLD = 200

# Score blend when both signals fire. Heuristic: substring is exact and
# rare → high precision but low recall; BM25 is fuzzier but covers the
# long tail.
W_SUBSTRING = 0.6
W_BM25 = 0.4

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


@dataclass
class IndexEntry:
    """One indexed knowledge document."""
    id: str
    path: str
    text: str
    title: str = ""
    tags: List[str] = field(default_factory=list)
    scope: str = ""    # "industry" / "project" / "global"
    type: str = ""     # "heuristic" / "glossary" / "page" ...

    def haystack(self) -> str:
        """All searchable text for this entry, lowercased."""
        return " ".join([self.title, self.text, " ".join(self.tags),
                         self.id, self.path]).lower()


@dataclass
class HybridRetriever:
    """Hybrid substring + BM25 retriever.

    The retriever is stateless until `index()` is called. Re-indexing
    resets everything; there is no incremental update API in v1.1.
    """
    entries: List[IndexEntry] = field(default_factory=list)
    _bm25: Optional[BM25Okapi] = field(default=None, repr=False)
    _tokenized: List[List[str]] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_entries(self, entries: Iterable[IndexEntry]) -> None:
        """Index already-loaded entries (used by tests + custom drivers)."""
        self.entries = list(entries)
        self._tokenized = [_tokenize(e.haystack()) for e in self.entries]
        if len(self.entries) >= BM25_THRESHOLD and self._tokenized:
            self._bm25 = BM25Okapi(self._tokenized)
        else:
            self._bm25 = None

    def index_dirs(self, dirs: Sequence[Path]) -> None:
        """Walk directories, load every .md/.yaml/.yml/.txt as one entry.

        Files starting with `_` are skipped (private/index files).
        """
        loaded: List[IndexEntry] = []
        for root in dirs:
            root = Path(root)
            if not root.exists():
                continue
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                if p.name.startswith("_"):
                    continue
                if p.suffix.lower() not in (".md", ".markdown",
                                            ".yaml", ".yml", ".txt"):
                    continue
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                # Title heuristic: first heading / filename
                title = p.stem
                for line in text.splitlines():
                    s = line.strip()
                    if s.startswith("#"):
                        title = s.lstrip("#").strip()
                        break
                # Scope/type heuristic: parent dir name
                parent = p.parent.name
                ent = IndexEntry(
                    id=str(p.relative_to(root)),
                    path=str(p),
                    text=text,
                    title=title,
                    scope=parent or "global",
                    type=p.suffix.lstrip("."),
                )
                loaded.append(ent)
        self.index_entries(loaded)

    # ------------------------------------------------------------------
    # Searching
    # ------------------------------------------------------------------

    def search(self, query: str, *, top_k: int = 5,
               scope: Optional[List[str]] = None,
               tags: Optional[List[str]] = None) -> List[dict]:
        """Return up to `top_k` hits as dicts:
            {"entry": IndexEntry, "score": float, "signals": {...}}
        """
        if not query or not self.entries:
            return []
        q_lower = query.lower().strip()
        q_tokens = _tokenize(query)

        # --- substring scores
        sub_scores: List[float] = []
        for e in self.entries:
            hay = e.haystack()
            if not q_lower:
                sub_scores.append(0.0)
                continue
            # Score = #unique-token-hits + small bonus for full-phrase hit
            unique_hits = sum(1 for tok in set(q_tokens) if tok in hay)
            phrase_bonus = 1.0 if q_lower in hay else 0.0
            sub_scores.append(unique_hits + phrase_bonus)

        # Normalize substring scores to [0,1]
        sub_max = max(sub_scores) or 1.0
        sub_norm = [s / sub_max for s in sub_scores]

        # --- BM25 (when corpus large enough)
        bm_norm: List[float]
        if self._bm25 is not None and q_tokens:
            bm_raw = self._bm25.get_scores(q_tokens)
            bm_max = max(bm_raw) or 1.0
            bm_norm = [s / bm_max for s in bm_raw]
        else:
            bm_norm = [0.0] * len(self.entries)

        # --- blend
        signals: List[dict] = []
        for i, _ in enumerate(self.entries):
            s_sub = sub_norm[i]
            s_bm = bm_norm[i]
            if self._bm25 is None:
                blended = s_sub
            else:
                blended = W_SUBSTRING * s_sub + W_BM25 * s_bm
            signals.append({"substring": s_sub, "bm25": s_bm,
                            "score": blended})

        # --- filter by scope/tags
        candidates = list(range(len(self.entries)))
        if scope:
            scope_set = set(scope)
            candidates = [i for i in candidates
                          if self.entries[i].scope in scope_set]
        if tags:
            tag_set = set(tags)
            candidates = [i for i in candidates
                          if tag_set.intersection(self.entries[i].tags)]

        # --- rank
        candidates.sort(key=lambda i: signals[i]["score"], reverse=True)
        # Drop hard zeros
        candidates = [i for i in candidates if signals[i]["score"] > 0]
        candidates = candidates[:top_k]

        return [
            {
                "entry": self.entries[i],
                "score": signals[i]["score"],
                "signals": {k: v for k, v in signals[i].items()
                            if k != "score"},
            }
            for i in candidates
        ]

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict:
        return {
            "indexed": len(self.entries),
            "bm25_active": self._bm25 is not None,
            "bm25_threshold": BM25_THRESHOLD,
        }
