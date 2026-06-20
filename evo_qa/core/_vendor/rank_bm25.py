# rank_bm25 — vendored from https://github.com/dorianbrown/rank_bm25
# Original copyright (c) Dorian Brown. Apache License 2.0.
# Trimmed to the BM25Okapi class only. No external deps (numpy not used).
"""Lightweight BM25Okapi for small corpora.

This is a stripped-down, numpy-free port. Suitable for 100s–10,000s of
short documents. For larger corpora consider the upstream package.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import List, Sequence


class BM25Okapi:
    """Okapi BM25.

    Parameters
    ----------
    corpus : list[list[str]]
        Tokenized documents.
    k1 : float
        Term frequency saturation parameter (default 1.5).
    b : float
        Length normalization (default 0.75).
    epsilon : float
        Floor for IDF when a term appears in nearly every document.
    """

    def __init__(self,
                 corpus: Sequence[Sequence[str]],
                 k1: float = 1.5,
                 b: float = 0.75,
                 epsilon: float = 0.25) -> None:
        self.k1 = k1
        self.b = b
        self.epsilon = epsilon

        self.corpus_size = len(corpus)
        self.doc_lens: List[int] = [len(d) for d in corpus]
        self.avgdl = (sum(self.doc_lens) / self.corpus_size
                      if self.corpus_size else 0.0)

        # term frequencies per doc
        self.doc_freqs: List[Counter] = [Counter(d) for d in corpus]

        # document frequency: number of docs containing each term
        df: Counter = Counter()
        for d in self.doc_freqs:
            for term in d.keys():
                df[term] += 1
        # IDF with the Robertson/Sparck-Jones flavor; floored by epsilon
        # to avoid negatives for terms that occur in almost all docs.
        self.idf: dict[str, float] = {}
        idf_sum = 0.0
        negative_idfs: list[str] = []
        for term, freq in df.items():
            v = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5))
            self.idf[term] = v
            idf_sum += v
            if v < 0:
                negative_idfs.append(term)
        avg_idf = (idf_sum / len(self.idf)) if self.idf else 0.0
        eps = self.epsilon * avg_idf
        for t in negative_idfs:
            self.idf[t] = eps

    def get_scores(self, query: Sequence[str]) -> List[float]:
        """Return BM25 score per document for a tokenized query."""
        scores = [0.0] * self.corpus_size
        for q in query:
            qi = self.idf.get(q)
            if qi is None:
                continue
            for i, freq in enumerate(self.doc_freqs):
                f = freq.get(q, 0)
                if not f:
                    continue
                dl = self.doc_lens[i]
                denom = f + self.k1 * (1 - self.b + self.b * dl /
                                       (self.avgdl or 1))
                scores[i] += qi * (f * (self.k1 + 1) / denom)
        return scores

    def get_top_n(self, query: Sequence[str], documents: Sequence,
                  n: int = 5) -> list:
        scores = self.get_scores(query)
        ranked = sorted(range(self.corpus_size),
                        key=lambda i: scores[i],
                        reverse=True)[:n]
        return [documents[i] for i in ranked]
