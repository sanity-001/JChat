"""Extraction: pluggable extractors under one protocol."""

from __future__ import annotations

import os

from JChat.memory.extract.base import ExtractedEntity, ExtractedRelation, Extraction
from JChat.memory.extract.llm import LLMExtractor
from JChat.memory.extract.rule import RuleExtractor
from JChat.memory.ontology import Ontology


def build_extractor(ontology: Ontology):
    """Pick the extractor by environment: LLM if a key is configured, else rules."""
    if os.getenv("MEMOKG_API_KEY") or os.getenv("OPENAI_API_KEY"):
        try:
            return LLMExtractor(ontology)
        except ValueError:
            pass
    return RuleExtractor(ontology)


__all__ = [
    "ExtractedEntity",
    "ExtractedRelation",
    "Extraction",
    "LLMExtractor",
    "RuleExtractor",
    "build_extractor",
]
