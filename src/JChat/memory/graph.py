"""KnowledgeGraph: NetworkX-based knowledge network with ontology-aware helpers."""

from __future__ import annotations

import networkx as nx

from JChat.memory.ontology import Ontology


def node_id(label: str, name: str) -> str:
    return f"{label}::{name}"


class KnowledgeGraph:
    """Edges and nodes of an ontology-typed knowledge graph backed by NetworkX.

    Node identity is ``EntityType::Name`` so that a Tool named "RAG" and a
    Concept named "RAG" never collide by accident.
    """

    def __init__(self, ontology: Ontology, graph: nx.MultiDiGraph | None = None):
        self.ontology = ontology
        self.graph: nx.MultiDiGraph = graph if graph is not None else nx.MultiDiGraph()

    # ------------------------------------------------------------------ write
    def add_entity(self, label: str, name: str, doc_id: int | None = None, importance: float = 1.0) -> str:
        if not name or not name.strip():
            raise ValueError("entity name must not be empty")
        nid = node_id(label, name)
        if not self.graph.has_node(nid):
            self.graph.add_node(nid, label=label, name=name, doc_id=doc_id, importance=importance)
        else:
            self.graph.nodes[nid].setdefault("doc_id", doc_id)
        return nid

    def add_relation(
        self,
        head: str,
        rel_type: str,
        tail: str,
        doc_id: int | None = None,
        weight: float = 1.0,
    ) -> None:
        for nid in (head, tail):
            if not self.graph.has_node(nid):
                label, name = nid.rsplit("::", 1)
                self.graph.add_node(nid, label=label, name=name, doc_id=doc_id)
        self.graph.add_edge(head, tail, key=rel_type, rel_type=rel_type, doc_id=doc_id, weight=weight)

    # ------------------------------------------------------------------- read
    def node_info(self, nid: str) -> dict:
        return dict(self.graph.nodes[nid]) if self.graph.has_node(nid) else {}

    def entities(self) -> list[dict]:
        return [{"node_id": nid, **dict(data)} for nid, data in self.graph.nodes(data=True)]

    def relations(self) -> list[dict]:
        out = []
        for u, v, key, data in self.graph.edges(keys=True, data=True):
            out.append(
                {
                    "head": u,
                    "tail": v,
                    "rel_type": key,
                    "head_name": self.graph.nodes[u].get("name", u),
                    "tail_name": self.graph.nodes[v].get("name", v),
                    **{k: val for k, val in data.items() if k not in ("name",)},
                }
            )
        return out

    def neighbors(self, name: str, rel_type: str | None = None, depth: int = 1) -> set[str]:
        """BFS up to ``depth`` hops from an entity by name, optionally edge-filtered.

        Matches either a bare entity name (unique across labels) or a full node id.
        """
        nid = self._locate(name)
        if nid is None:
            return set()
        seen = {nid}
        frontier = [(nid, 0)]
        while frontier:
            current, level = frontier.pop(0)
            if level >= depth:
                continue
            for u, v, key in self.graph.edges(keys=True, data=False):
                if u == current:
                    nxt, rel = v, key
                elif v == current:
                    nxt, rel = u, key
                else:
                    continue
                if rel_type is not None and rel != rel_type:
                    continue
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append((nxt, level + 1))
        return seen - {nid}

    def _locate(self, name: str) -> str | None:
        if self.graph.has_node(name):
            return name
        for nid in self.graph.nodes:
            if self.graph.nodes[nid].get("name") == name:
                return nid
        return None

    # -------------------------------------------------------------- doc scopes
    def relations_of_doc(self, doc_id: int) -> list[dict]:
        return [r for r in self.relations() if r.get("doc_id") == doc_id]

    def remove_doc_subgraph(self, doc_id: int) -> None:
        for u, v, key, data in list(self.graph.edges(keys=True, data=True)):
            if data.get("doc_id") == doc_id:
                self.graph.remove_edge(u, v, key=key)
        for nid in list(self.graph.nodes):
            if self.graph.degree(nid) == 0 and self.graph.nodes[nid].get("doc_id") == doc_id:
                self.graph.remove_node(nid)

    # ------------------------------------------------------------- analytics
    def analyze(self) -> dict:
        """Cheap but instructive structural stats: centrality, hub score, communities.

        The hub score is our own pagerank-flavored measure (incoming weight
        mass) — pure-Python, so `analyze()` runs without scipy.
        """
        if self.graph.number_of_nodes() == 0:
            return {"node_count": 0}
        degree = nx.degree_centrality(self.graph)
        hub = {nid: 0.0 for nid in self.graph.nodes}
        total = 0.0
        data = self.graph.edges(data=True)
        for _u, _v, attrs in data:
            hub[_v] += float(attrs.get("weight", 1.0))
            total += float(attrs.get("weight", 1.0))
        top_hub = sorted(hub.items(), key=lambda kv: kv[1], reverse=True)[:5]
        communities = nx.community.greedy_modularity_communities(self.graph)
        return {
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
            "top_degree": sorted(degree.items(), key=lambda kv: kv[1], reverse=True)[:5],
            "top_hub": top_hub,
            "total_weight": total,
            "community_count": len(communities),
            "communities": sorted((sorted(c) for c in communities), key=len, reverse=True),
            "density": nx.density(self.graph),
        }

    def embedding_snapshot(self) -> dict[str, str]:
        """node_id -> its plain name, used to align vector search hits with graph sites."""
        return {nid: data.get("name", nid) for nid, data in self.graph.nodes(data=True)}

    def __contains__(self, nid: str) -> bool:
        return nid in self.graph

    def __len__(self) -> int:
        return self.graph.number_of_nodes()
