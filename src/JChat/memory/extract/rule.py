"""RuleExtractor: deterministic, offline, zero-dependency entity/relation extraction.

Ships to keep MemoKG runnable without an LLM key, as fixture for tests, and as
a baseline extractor for the hybrid-search quality story:
* entities  — capitalized acronyms/terms plus ontology keywords, deduped
* relations — ontology patterns phrased as '<Agent> <pattern> <Target>'

Deliberately simple: it never claims to match LLM quality, only to be
deterministic and honest about what it misses.
"""

from __future__ import annotations

import re
from collections import Counter

from JChat.memory.documents import Document
from JChat.memory.extract.base import ExtractedEntity, ExtractedRelation, Extraction
from JChat.memory.ontology import Ontology

_CAPS = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:[A-Za-z0-9]*))\b")
_CJK = re.compile(r"([\u4e00-\u9fff]{2,8}(?:概念|工具|论文|方法|框架|作者))")
_NOISE = {
    "the",
    "this",
    "that",
    "these",
    "our",
    "its",
    "and",
    "or",
    "but",
    "not",
    "it",
    "with",
    "from",
    "into",
    "via",
    "over",
    "under",
    "only",
    "both",
    "recent",
    "inside",
    "during",
    "however",
    "another",
    "first",
    "second",
    "third",
    "also",
    "they",
}


class RuleExtractor:
    def __init__(self, ontology: Ontology):
        self.ontology = ontology
        self._patterns: list[tuple[str, str]] = []
        for rt in self.ontology.relation_types.values():
            for p in rt.patterns:
                self._patterns.append((p.lower(), rt.name))
        self._keyword_label: dict[str, str] = {}
        for et in self.ontology.entity_types.values():
            for kw in et.keywords:
                self._keyword_label[kw.lower()] = et.name

    def extract(self, document: Document) -> Extraction:
        text = document.text
        candidates = [t for t in _CAPS.findall(text)]
        candidates = [t for t in candidates if _keep(t, text)]
        for kw in self._keyword_label:
            if kw in text.lower() and kw not in {c.lower() for c in candidates}:
                candidates.append(kw)
        for m in _CJK.findall(text):
            candidates.append(m)
        frequency = Counter(candidates)
        names = [n for n, _ in frequency.most_common()]
        entities = [ExtractedEntity(label=self._label_for(n), name=n) for n in names]

        relations: list[ExtractedRelation] = []
        lowered = text.lower()
        entity_names = [n for n in names]
        for pattern, rel_name in self._patterns:
            for m in re.finditer(re.escape(pattern), lowered):
                head = _preceding_term(lowered, m.start(), entity_names)
                tail = _following_term(lowered, m.end(), entity_names)
                if head and tail and head != tail:
                    relations.append(ExtractedRelation(head=head, rel_type=rel_name, tail=tail))
        return Extraction(entities=entities, relations=_dedupe(relations))

    def _label_for(self, name: str) -> str:
        return self._keyword_label.get(name.lower(), "Concept")


def _keep(token: str, text: str) -> bool:
    """Drop obvious non-entities: too-simple, sentence-start noise, or filler."""
    if len(token) < 2:
        return False
    if token.lower() in _NOISE:
        return False
    if token.isupper():
        return len(token) >= 3  # keep real acronyms like RAG, FAISS
    return True


def _preceding_term(text: str, pos: int, names: list[str]) -> str | None:
    found: list[tuple[int, str]] = []
    for name in names:
        idx = text.rfind(name.lower(), 0, pos)
        if idx >= 0 and pos - idx <= len(name) + 24:
            found.append((pos - (idx + len(name.lower())), name))
    if not found:
        return None
    return min(found, key=lambda kv: kv[0])[1]


def _following_term(text: str, pos: int, names: list[str]) -> str | None:
    found: list[tuple[int, str]] = []
    for name in names:
        idx = text.find(name.lower(), pos, pos + len(name) + 40)
        if idx >= 0:
            found.append((idx, -len(name.lower()), name))
    if not found:
        return None
    return min(found, key=lambda kv: (kv[0], kv[1]))[2]


def _dedupe(relations: list[ExtractedRelation]) -> list[ExtractedRelation]:
    seen: set[tuple[str, str, str]] = set()
    out: list[ExtractedRelation] = []
    for r in relations:
        key = (r.head, r.rel_type, r.tail)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out
