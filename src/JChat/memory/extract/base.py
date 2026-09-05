"""Extractor protocol: documents in, structured entities+relations out."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from JChat.memory.documents import Document


@dataclass(frozen=True)
class ExtractedEntity:
    label: str
    name: str


@dataclass(frozen=True)
class ExtractedRelation:
    head: str  # entity name
    rel_type: str  # one of ontology.relation_types
    tail: str  # entity name


@dataclass
class Extraction:
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)

    def merge(self, other: Extraction) -> Extraction:
        seen_e = {(e.label, e.name) for e in self.entities}
        for e in other.entities:
            if (e.label, e.name) not in seen_e:
                self.entities.append(e)
                seen_e.add((e.label, e.name))
        seen_r = {(r.head, r.rel_type, r.tail) for r in self.relations}
        for r in other.relations:
            if (r.head, r.rel_type, r.tail) not in seen_r:
                self.relations.append(r)
                seen_r.add((r.head, r.rel_type, r.tail))
        return self

    @classmethod
    def empty(cls) -> Extraction:
        return cls()


class Extractor(Protocol):
    ontology: object

    def extract(self, document: Document) -> Extraction: ...
