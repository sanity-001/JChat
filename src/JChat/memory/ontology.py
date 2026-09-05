"""Ontology: the schema that tells the extractor *what* to look for and *how* to link it.

The ontology is the single control point between "free text" and "structured
knowledge". MemoKG ships a default tech-domain ontology (`default_tech()`);
users can declare their own labels, relation types and keyword clues.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntityType:
    """A node category the extractor may emit (e.g. Tool, Paper)."""

    name: str
    description: str = ""
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelationType:
    """A labeled edge category (e.g. 'A is based on B')."""

    name: str
    description: str = ""
    patterns: tuple[str, ...] = ()


class Ontology:
    """A container of entity/relation types.

    A canonical relation from A to B is written ``A <name> B``; the
    ``description``/``patterns`` guide both the LLM and the rule-based extractor.
    """

    def __init__(
        self,
        entity_types: list[EntityType] | None = None,
        relation_types: list[RelationType] | None = None,
    ):
        self.entity_types: dict[str, EntityType] = {}
        self.relation_types: dict[str, RelationType] = {}
        for et in entity_types or []:
            self.add_entity_type(et)
        for rt in relation_types or []:
            self.add_relation_type(rt)

    def add_entity_type(self, et: EntityType) -> Ontology:
        if et.name in self.entity_types:
            raise ValueError(f"duplicate entity type: {et.name}")
        self.entity_types[et.name] = et
        return self

    def add_relation_type(self, rt: RelationType) -> Ontology:
        if rt.name in self.relation_types:
            raise ValueError(f"duplicate relation type: {rt.name}")
        self.relation_types[rt.name] = rt
        return self

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Ontology(entity_types={sorted(self.entity_types)}, "
            f"relation_types={sorted(self.relation_types)})"
        )

    def as_schema_json(self) -> dict:
        """Stable JSON view injected into the LLM prompt template."""
        return {
            "entity_types": [
                {"name": et.name, "description": et.description} for et in self.entity_types.values()
            ],
            "relation_types": [
                {"name": rt.name, "description": rt.description} for rt in self.relation_types.values()
            ],
        }


def default_tech() -> Ontology:
    """A ready-made ontology for technical/scientific knowledge bases."""
    return Ontology(
        entity_types=[
            EntityType("Concept", "an abstract idea, principle or phenomenon", ("relevance",)),
            EntityType("Tool", "software, library or platform", ("framework",)),
            EntityType("Framework", "a scaffold of libraries with conventions", ("framework",)),
            EntityType("Paper", "a publication, article or arXiv reprint"),
            EntityType("Author", "a person who wrote a paper or article"),
            EntityType("Method", "a technique, algorithm or procedure"),
        ],
        relation_types=[
            RelationType("implements", "A implements B — A provides B's functionality", ("implements",)),
            RelationType(
                "based_on",
                "A is based on B — A builds on top of B",
                ("is based on", "built on", "built upon", "stems from"),
            ),
            RelationType(
                "outperforms",
                "A outperforms B — A beats B in some measure",
                ("outperforms", "outperformed"),
            ),
            RelationType(
                "used_in",
                "A is used in B — A is utilized in the context of B",
                ("used in", "utilized in", "uses", "powers"),
            ),
            RelationType("proposes", "A proposes B — A introduces B", ("proposes", "introduced")),
        ],
    )
