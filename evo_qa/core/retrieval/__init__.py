"""Hybrid retrieval over the knowledge base.

v1.1 design
-----------
- Always: case-insensitive substring match (cheap, exact, predictable).
- Above 200 entries: also score with vendored BM25, blend.

Why hybrid:
  Substring is unbeatable for short corpora and exact-keyword recall
  ("Login button"). BM25 takes over when substring quality collapses
  (5000+ entries, ambiguous queries).

Usage
-----
    from evo_qa.core.retrieval import HybridRetriever
    r = HybridRetriever()
    r.index([Path("references/knowledge")])
    hits = r.search("login button selector", top_k=5)
"""
from .hybrid import HybridRetriever, IndexEntry, _tokenize  # noqa: F401

__all__ = ["HybridRetriever", "IndexEntry"]
