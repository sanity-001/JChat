"""Vector index: dense-enough lexical embeddings with a pluggable adapter.

Default: TF-IDF over a Chinese/English tokenizer (pure numpy, zero heavy
deps). Optional: sentence-transformers adapter for real semantic search
(MEMOKG_EMBEDDING=sentence-transformers). Both expose the same tiny protocol.
"""

from __future__ import annotations

import math
import os
import re
from collections import defaultdict
from typing import Protocol

_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9_+.#-]*")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """ASCII words + CJK bigrams (unigrams for short runs)."""
    tokens: list[str] = []
    for w in _WORD.findall(text):
        tokens.append(w.lower())
    for run in _CJK_RUN.findall(text):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


class VectorIndex(Protocol):
    def similarity(self, query: str, k: int = 5) -> list[tuple[int, float]]:
        """Top-k docs by cosine similarity: [(doc_id, score), ...] score in (0, 1]."""
        ...

    def text_of(self, doc_id: int) -> str | None: ...


class TfIdfIndex:
    def __init__(self, docs: list[tuple[int, str]] | None = None):
        self.doc_ids: list[int] = []
        self.texts: dict[int, str] = {}
        self.vectors: dict[int, dict[str, float]] = {}
        self.doc_freq: dict[str, int] = {}
        self.tokens_by_doc: dict[int, set[str]] = {}
        if docs:
            self.fit(docs)

    def fit(self, docs: list[tuple[int, str]]) -> TfIdfIndex:
        self.doc_ids = [d for d, _ in docs]
        self.texts = {d: t for d, t in docs}
        self.tokens_by_doc = {d: set(tokenize(t)) for d, t in docs}
        doc_freq: defaultdict[str, int] = defaultdict(int)
        for toks in self.tokens_by_doc.values():
            for raw in toks:
                doc_freq[raw.lower()] += 1
        self.doc_freq = dict(doc_freq)
        n_docs = max(len(docs), 1)
        self.vectors = {}
        for d, toks in self.tokens_by_doc.items():
            tf: defaultdict[str, int] = defaultdict(int)
            for t in toks:
                tf[t] += 1
            self.vectors[d] = {
                t: (1 + math.log(count)) * math.log(n_docs / self.doc_freq[t] if self.doc_freq[t] else 1)
                for t, count in tf.items()
            }
        self._norm: dict[int, float] = {
            d: math.sqrt(sum(w * w for w in vec.values()) or 1.0) for d, vec in self.vectors.items()
        }
        return self

    def _query_vector(self, query: str) -> dict[str, float]:
        tf: defaultdict[str, int] = defaultdict(int)
        for t in tokenize(query):
            tf[t] += 1
        n_docs = max(len(self.doc_ids), 1)
        vec = {}
        for t, count in tf.items():
            if t in self.doc_freq:
                vec[t] = (1 + math.log(count)) * math.log(n_docs / self.doc_freq[t])
        return vec

    def similarity(self, query: str, k: int = 5) -> list[tuple[int, float]]:
        qvec = self._query_vector(query)
        if not qvec or not self.vectors:
            return []
        qnorm = math.sqrt(sum(w * w for w in qvec.values()) or 1.0)
        scored: list[tuple[int, float]] = []
        for d, vec in self.vectors.items():
            dot = sum(qvec.get(t, 0.0) * w for t, w in vec.items())
            if dot > 0:
                scored.append((d, dot / (qnorm * self._norm[d])))
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored[:k]

    def text_of(self, doc_id: int) -> str | None:
        return self.texts.get(doc_id)


class SentenceTransformerIndex:
    """Adapter using sentence-transformers when MEMOKG_EMBEDDING=sentence-transformers."""

    def __init__(self, docs: list[tuple[int, str]], model: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError("pip install memo-kg[embeddings] to use sentence-transformers") from exc
        self.model = SentenceTransformer(model)
        self.doc_ids = [d for d, _ in docs]
        self.texts = {d: t for d, t in docs}
        self.embeddings = self.model.encode([t for _, t in docs], normalize_embeddings=True)

    def similarity(self, query: str, k: int = 5) -> list[tuple[int, float]]:
        import numpy as np

        q = self.model.encode([query], normalize_embeddings=True)[0]
        scores = self.embeddings @ q
        order = np.argsort(-scores)[:k]
        return [(self.doc_ids[int(i)], float(scores[i])) for i in order if scores[i] > 0]

    def text_of(self, doc_id: int) -> str | None:
        return self.texts.get(doc_id)


def build_vector_index(docs: list[tuple[int, str]]) -> VectorIndex:
    backend = os.getenv("MEMOKG_EMBEDDING", "tfidf").strip().lower()
    if backend == "sentence-transformers":
        try:
            return SentenceTransformerIndex(docs)
        except RuntimeError:
            pass
    return TfIdfIndex(docs)
