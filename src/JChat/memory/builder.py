"""KnowledgeGraphBuilder: documents in, knowledge graph out — incrementally.

The builder owns the write path. Every document is fingerprinted; unchanged
documents are skipped, changed documents only re-extract their own subgraph,
and deleted documents prune their triples. The in-memory NetworkX graph is a
mirror rebuilt from the store after each ingest step.
"""

from __future__ import annotations

from pathlib import Path

from JChat.memory.documents import Document, load_documents
from JChat.memory.extract import build_extractor
from JChat.memory.extract.base import Extractor
from JChat.memory.graph import KnowledgeGraph, node_id
from JChat.memory.ontology import Ontology
from JChat.memory.storage import SQLiteStore


class KnowledgeGraphBuilder:
    def __init__(
        self,
        ontology: Ontology,
        extractor: Extractor | None = None,
        store: SQLiteStore | None = None,
    ):
        self.ontology = ontology
        self.extractor = extractor or build_extractor(ontology)
        self.store = store if store is not None else SQLiteStore()
        self.graph = KnowledgeGraph(ontology)
        self.rebuild_graph()

    # ------------------------------------------------------------- public API
    def build_from_documents(self, paths: list[str | Path]) -> KnowledgeGraph:
        for doc in load_documents(paths):
            self._ingest(doc)
        return self.graph

    def build_from_texts(self, name_texts: dict[str, str]) -> KnowledgeGraph:
        for name, text in name_texts.items():
            self._ingest(Document(name=name, text=text))
        return self.graph

    def build_from_document(self, doc: Document) -> KnowledgeGraph:
        self._ingest(doc)
        return self.graph

    def remove_document(self, path: str) -> None:
        if self.store.delete_doc(path) is not None:
            self.rebuild_graph()

    def rebuild_graph(self) -> KnowledgeGraph:
        nodes, edges = self.store.load_graph_rows()
        graph = KnowledgeGraph(self.ontology)
        for nid, label, name, doc_id, importance in nodes:
            graph.graph.add_node(nid, label=label, name=name, doc_id=doc_id, importance=importance)
        for head, rel_type, tail, doc_id, weight in edges:
            graph.graph.add_edge(head, tail, key=rel_type, rel_type=rel_type, doc_id=doc_id, weight=weight)
        self.graph = graph
        return graph

    def find(self, name: str) -> dict | None:
        nid = _locate(self.graph, name)
        return self.graph.node_info(nid) if nid else None

    def analyze(self) -> dict:
        return self.graph.analyze()

    # ------------------------------------------------------------------ internals
    def _ingest(self, doc: Document) -> None:
        doc_id, changed = self.store.upsert_doc(doc.name, doc.text)
        if not changed:
            return
        self.store.clear_doc_graph(doc_id)
        extraction = self.extractor.extract(doc)
        labels: dict[str, str] = {}
        for ent in extraction.entities:
            labels[ent.name] = ent.label
            self.store.save_node(node_id(ent.label, ent.name), ent.label, ent.name, doc_id, 1.0)
        for rel in extraction.relations:
            head_label = labels.get(rel.head, "Concept")
            tail_label = labels.get(rel.tail, "Concept")
            self.store.save_relation(
                node_id(head_label, rel.head),
                rel.rel_type,
                node_id(tail_label, rel.tail),
                doc_id,
                1.0,
            )
        self.store.commit()
        self.rebuild_graph()


def _locate(graph: KnowledgeGraph, name: str) -> str | None:
    if graph.graph.has_node(name):
        return name
    for nid in graph.graph.nodes:
        if graph.graph.nodes[nid].get("name") == name:
            return nid
    return None
