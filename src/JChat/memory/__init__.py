"""MemoKG — a knowledge-graph-based long-term memory framework for AI agents."""

from JChat.memory.builder import KnowledgeGraphBuilder
from JChat.memory.graph import KnowledgeGraph
from JChat.memory.memory import AgentMemory
from JChat.memory.ontology import EntityType, Ontology, RelationType, default_tech
from JChat.memory.retriever import HybridRetriever
from JChat.memory.storage import SQLiteStore
from JChat.memory.vector import build_vector_index

__version__ = "0.1.0"

__all__ = [
    "AgentMemory",
    "EntityType",
    "HybridRetriever",
    "KnowledgeGraph",
    "KnowledgeGraphBuilder",
    "Ontology",
    "RelationType",
    "SQLiteStore",
    "build_vector_index",
    "default_tech",
]
