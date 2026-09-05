"""HybridRetriever: vector search + graph traversal fused with Reciprocal Rank Fusion.

Pipeline: query → entity linking (where does the query sit in the graph?)
→ graph expansion → vector similarity → RRF fusion → RAG context assembly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from JChat.memory.graph import KnowledgeGraph
from JChat.memory.vector import VectorIndex


@dataclass
class Hit:
    doc_id: int
    score: float = 0.0
    source: str = "hybrid"
    name: str = ""
    snippet: str = ""

    def __repr__(self) -> str:  # pragma: no cover
        return f"Hit(doc={self.doc_id}, score={self.score:.4f}, {self.source})"


@dataclass
class GraphHit:
    node_id: str
    name: str
    label: str
    depth: int
    via: tuple[str, str] = ("", "")

    def __repr__(self) -> str:  # pragma: no cover
        return f"GraphHit({self.name}, depth={self.depth})"


@dataclass
class QueryUnderstanding:
    entities: list[dict] = field(default_factory=list)
    neighbors: list[GraphHit] = field(default_factory=list)


_WORD_BOUNDARY = re.compile(r"[a-z0-9]+")


class HybridRetriever:
    def __init__(self, graph: KnowledgeGraph, vector_index: VectorIndex, rrf_k: int = 60):
        self.graph = graph
        self.vector_index = vector_index
        self.rrf_k = rrf_k
        self._doc_names: dict[str, set[int]] = self._build_name_doc_lookup()

    def _build_name_doc_lookup(self) -> dict[str, set[int]]:
        lookup: dict[str, set[int]] = {}
        names = {data.get("name") for data in self.graph.graph.nodes.values()}
        for doc_id, text in [(d, t) for t, d in self._texts_with_ids()]:
            lowered = text.lower()
            for name in names:
                if name and name.lower() in lowered:
                    lookup.setdefault(name.lower(), set()).add(doc_id)
        return lookup

    def _texts_with_ids(self) -> list[tuple[str, int]]:
        return [
            (self.vector_index.text_of(doc_id) or "", doc_id)
            for doc_id in getattr(self.vector_index, "doc_ids", [])
        ]

    # ------------------------------------------------------------------ vector
    def semantic_search(self, query: str, k: int = 5) -> list[Hit]:
        hits = []
        for doc_id, score in self.vector_index.similarity(query, k=k):
            hits.append(Hit(doc_id=doc_id, score=score, source="vector"))
        self._attach_names(hits)
        return hits

    # -------------------------------------------------------------------- graph
    def graph_search(
        self, entity: str, rel_type: str | None = None, depth: int = 2, k: int = 10
    ) -> list[GraphHit]:
        """Hop outwards from an entity name (either direction), optionally edge-filtered."""
        start = _locate(self.graph, entity)
        if start is None:
            return []
        frontier: list[tuple[str, int, tuple[str, str]]] = [(start, 0, ("", ""))]
        seen: set[str] = {start}
        results: list[GraphHit] = []
        while frontier:
            current, level, via = frontier.pop(0)
            if level >= depth:
                continue
            for prev, cand, rel in _neighbors_by(self.graph, current):
                if rel_type is not None and rel != rel_type:
                    continue
                if cand not in seen:
                    seen.add(cand)
                    results.append(
                        GraphHit(
                            node_id=cand,
                            name=self.graph.graph.nodes[cand].get("name", cand),
                            label=self.graph.graph.nodes[cand].get("label", ""),
                            depth=level + 1,
                            via=(prev, rel),
                        )
                    )
                    frontier.append((cand, level + 1, (current, rel)))
        results.sort(key=lambda h: (h.depth, -len(self._doc_names.get(h.name.lower(), set()))))
        return results[:k]

    # ------------------------------------------------------------- query pieces
    def entity_link(self, query: str) -> list[dict]:
        linked = []
        lowered = query.lower()
        words = {w for w in _WORD_BOUNDARY.findall(lowered)}
        for nid, data in self.graph.graph.nodes(data=True):
            name = str(data.get("name", ""))
            if not name:
                continue
            name_l = name.lower()
            if name_l == lowered or name_l in lowered or any(w.startswith(name_l) for w in words):
                linked.append({"node_id": nid, "label": data.get("label", ""), "name": name})
        return linked

    def query_understanding(self, query: str, depth: int = 2) -> QueryUnderstanding:
        entities = self.entity_link(query)
        neighbors: list[GraphHit] = []
        for ent in entities:
            for hit in self.graph_search(ent["name"], depth=depth, k=20):
                if all(hit.node_id != n.node_id for n in neighbors):
                    neighbors.append(hit)
        return QueryUnderstanding(entities=entities, neighbors=neighbors)

    # ---------------------------------------------------------------- hybrid
    def hybrid_search(self, query: str, k: int = 5, depth: int = 2) -> list[Hit]:
        understanding = self.query_understanding(query, depth=depth)
        vector_hits = self.semantic_search(query, k=max(k * 4, 12))
        graph_ranks: dict[int, int] = {}

        boosted_names = {e["name"] for e in understanding.entities}
        for hit in understanding.neighbors:
            boosted_names.add(hit.name)
        matched: dict[int, int] = {}
        for doc_id in self._docs_for_names(boosted_names):
            matched[doc_id] = matched.get(doc_id, 0) + 1
        for position, doc_id in enumerate(sorted(matched, key=matched.get, reverse=True)):
            graph_ranks[doc_id] = position + 1

        fused = self._rrf([vector_hits, self._hits_from_ranks(graph_ranks)])
        out: list[Hit] = []
        for doc_id, score in fused[:k]:
            text = self.vector_index.text_of(doc_id) or ""
            out.append(
                Hit(
                    doc_id=doc_id,
                    score=score,
                    source="hybrid",
                    snippet=text[:160].replace("\n", " "),
                )
            )
        return out

    def _hits_from_ranks(self, ranks: dict[int, int]) -> list[Hit]:
        return [Hit(doc_id=doc_id, score=1.0, source="graph") for doc_id in sorted(ranks, key=ranks.get)]

    def _rrf(self, lists: list[list[Hit]]) -> list[tuple[int, float]]:
        scores: dict[int, float] = {}
        for doc_ids in lists:
            for rank, hit in enumerate(doc_ids):
                scores[hit.doc_id] = scores.get(hit.doc_id, 0.0) + 1.0 / (self.rrf_k + rank + 1)
        return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

    def _docs_for_names(self, names: set[str]) -> set[int]:
        docs: set[int] = set()
        for name in names:
            docs |= self._doc_names.get(name.lower(), set())
        return docs

    def _attach_names(self, hits: list[Hit]) -> None:
        for hit in hits:
            text = self.vector_index.text_of(hit.doc_id) or ""
            hit.name = _first_titleish(text) or text[:40].replace("\n", " ")

    # ------------------------------------------------------------------ RAG
    def context(
        self,
        hits: list[Hit],
        understanding: QueryUnderstanding | None = None,
        top: int = 3,
        limit: int = 12,
    ) -> str:
        """Assemble a RAG-friendly context: top doc snippets + relevant graph triples."""
        parts: list[str] = []
        for hit in hits[:top]:
            text = self.vector_index.text_of(hit.doc_id) or ""
            parts.append(f"[doc:{hit.doc_id}] {_clip(text, 1000)}")
        names: set[str] = set()
        if understanding is not None:
            names = {e["name"] for e in understanding.entities}
            names |= {n.name for n in understanding.neighbors}
        triples = "\n".join(
            f"{r['head_name']} --{r['rel_type']}--> {r['tail_name']}" for r in self._triples_for(names, limit)
        )
        if triples:
            parts.append("[knowledge-graph]\n" + triples)
        return "\n\n".join(parts)

    def _triples_for(self, names: set[str], limit: int) -> list[dict]:
        if not names:
            return []
        out = []
        for r in self.graph.relations():
            if r["head_name"] in names or r["tail_name"] in names:
                out.append(r)
            if len(out) >= limit:
                break
        return out


def _neighbors_by(graph: KnowledgeGraph, nid: str) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for u, _v, key, _data in graph.graph.in_edges(nid, keys=True, data=True):
        out.append((nid, u, key))
    for _u, v, key, _data in graph.graph.out_edges(nid, keys=True, data=True):
        out.append((nid, v, key))
    return out


def _locate(graph: KnowledgeGraph, name: str) -> str | None:
    if graph.graph.has_node(name):
        return name
    for nid in graph.graph.nodes:
        if graph.graph.nodes[nid].get("name") == name:
            return nid
    return None


def _first_titleish(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and len(stripped) < 80 and not any(c in stripped for c in "。.!?"):
            return stripped[:80]
    return None


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "..."
