"""AgentMemory: working/short/long-term memory with decay, consolidation and
contradiction detection.

Memory score = f(importance, access_count, age) — the exponential decay makes
memories fade unless accessed; consolidation promotes what stayed relevant,
and recall respects the graph-linked entity names for cross-session recall.
"""

from __future__ import annotations

import json
import math
import uuid

from JChat.memory.storage import SQLiteStore
from JChat.memory.vector import tokenize

_NEG = ("不喜欢", "讨厌", "不要", "再也不", "avoid", "dislike", "hate", "反对", "退出")
_POS = ("喜欢", "偏好", "想要", "prefer", "like", "want", "倾向", "酷爱", "感兴趣")


class AgentMemory:
    def __init__(self, store: SQLiteStore | None = None, working_window: int = 10, decay_rate: float = 0.01):
        self.store = store if store is not None else SQLiteStore()
        self.working_window = working_window
        self.decay_rate = decay_rate
        self.staging: list[dict] = []
        from JChat.memory.semantic import SemanticMemoryIndex

        self._sem = SemanticMemoryIndex()
        self._sem_dirty = True

    # ------------------------------------------------------------------ write
    def remember(self, content: str, entity_names: list[str] | None = None, importance: float = 3.0) -> str:
        memory_id = uuid.uuid4().hex
        self.store.save_memory(
            memory_id=memory_id,
            scope="short",
            content=content,
            entities=entity_names or [],
            importance=importance,
            score=self._score(importance=importance, access_count=0),
        )
        self.staging.append({"memory_id": memory_id, "content": content})
        self._sem_dirty = True
        if len(self.staging) > self.working_window:
            self.staging.pop(0)
        return memory_id

    def remember_summary(self, content: str, importance: float = 8.0) -> str:
        """常驻'近期生活摘要'（scope=summary）：注入走摘要带，不参与 recall 检索。"""
        memory_id = uuid.uuid4().hex
        self.store.save_memory(
            memory_id=memory_id,
            scope="summary",
            content=content,
            entities=[],
            importance=importance,
        )
        return memory_id

    # ------------------------------------------------------------------- read
    def recall(self, query: str, k: int = 5) -> list[dict]:
        """混合检索：语义余弦（0.6，可用时）+ token 重叠（0.4）+ 实体链接加分。"""
        q_tokens = set(tokenize(query))
        candidates = [
            self._enrich(m) for m in self.store.list_memories() if m["scope"] != "summary"
        ]
        sem_scores: dict[str, float] = {}
        if self._sem_dirty:
            self._sem.rebuild([(m["memory_id"], m["content"]) for m in candidates])
            self._sem_dirty = False
        if self._sem.available():
            sem_scores = dict(self._sem.top(query, k=len(candidates) or 1))
        scored: list[dict] = []
        q_entities = _entity_tokens(query)
        for m in candidates:
            content_tokens = set(tokenize(m["content"]))
            overlap = _overlap(q_tokens, content_tokens)
            sim = overlap
            if m["memory_id"] in sem_scores:
                cos01 = (sem_scores[m["memory_id"]] + 1) / 2  # [-1,1] → [0,1]
                sim = 0.6 * cos01 + 0.4 * overlap
            if q_entities:
                shared_entities = sum(1 for e in m["entities"] if _contains(e.lower(), query.lower()))
                sim += 0.3 * shared_entities
            if sim <= 0:
                continue
            m["_sim"] = sim
            m["_final"] = sim * (0.5 + 0.5 * min(1.0, m["score"] / 5.0))
            scored.append(m)
        scored.sort(key=lambda m: (m["_final"], m["last_access_at"]), reverse=True)
        for m in scored[:k]:
            self.store.touch_memory(m["memory_id"], m["score"])
        return scored[:k]

    def state(self, scope: str | None = None) -> list[dict]:
        return [self._enrich(m) for m in self.store.list_memories(scope)]

    def list_summaries(self) -> list[dict]:
        """常驻摘要带条目（按时间升序：最老在前）。"""
        rows = [self._enrich(m) for m in self.store.list_memories("summary")]
        rows.sort(key=lambda m: m["created_at"])
        return rows

    # -------------------------------------------------------------- lifecycle
    def decay(self, now: float | None = None) -> None:
        """Recompute scores from scratch: importance * exp(-rate * age) + access bonus."""
        for m in self.store.list_memories():
            self.store.update_memory_score(
                m["memory_id"],
                self._score(m["importance"], m["access_count"], m["last_access_at"], now),
            )

    def consolidate(self, promo_floor: float = 2.0) -> dict:
        """'Sleep-strip' pass: decay, then short-term memories still relevant
        are promoted to long-term; decaying ones surface as demoted."""
        self.decay()
        promoted = demoted = 0
        for m in self.store.list_memories():
            score = m["score"]
            if m["scope"] == "short" and score >= promo_floor:
                self.store.set_memory_scope(m["memory_id"], "long", score)
                promoted += 1
            elif m["scope"] == "long" and score < promo_floor * 0.5:
                demoted += 1
        return {"promoted": promoted, "demoted": demoted}

    # ------------------------------------------------------------- detection
    def check_contradictions(self, similarity_threshold: float = 0.85) -> list[dict]:
        memories = self.store.list_memories()
        found: list[dict] = []
        for i in range(len(memories)):
            for j in range(i + 1, len(memories)):
                a, b = memories[i], memories[j]
                if not set(a["entities"]) & set(b["entities"]):
                    continue
                sim = _overlap(set(tokenize(a["content"])), set(tokenize(b["content"])))
                if sim < similarity_threshold:
                    continue
                pa, pb = _polarity(a["content"]), _polarity(b["content"])
                if pa != 0 and pa != pb:
                    found.append(
                        {
                            "memory_a": a["memory_id"],
                            "memory_b": b["memory_id"],
                            "content_a": a["content"],
                            "content_b": b["content"],
                            "similarity": sim,
                            "reason": "opposite sentiment on shared entity",
                        }
                    )
        return found

    # ----------------------------------------------------------------- export
    def export(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.store.list_memories(), fh, ensure_ascii=False, indent=2)

    def import_memories(self, path: str) -> int:
        with open(path, encoding="utf-8") as fh:
            rows = json.load(fh)
        for m in rows:
            self.store.save_memory(
                memory_id=m["memory_id"],
                scope=m.get("scope", "long"),
                content=m["content"],
                entities=m.get("entities", []),
                importance=m.get("importance", 3.0),
                created_at=m.get("created_at"),
                last_access_at=m.get("last_access_at"),
                access_count=m.get("access_count", 0),
                score=m.get("score", 0.0),
            )
        return len(rows)

    # --------------------------------------------------------------- helpers
    def _score(
        self,
        importance: float,
        access_count: int,
        last_access_at: float | None = None,
        now: float | None = None,
    ) -> float:
        import time

        last = last_access_at or time.time()
        age_days = max(0.0, ((now or time.time()) - last) / 86400.0)
        return importance * math.exp(-self.decay_rate * age_days) + 0.5 * math.log10(1 + access_count)

    def _enrich(self, m: dict) -> dict:
        return m


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _entity_tokens(query: str) -> list[str]:
    return [w for w in query.split() if w[:1].isupper()]


def _contains(needle: str, haystack: str) -> bool:
    return bool(needle) and needle.lower() in haystack.lower()


def _polarity(text: str) -> int:
    """Negators dominate: '不喜欢' is negative even though it contains '喜欢'."""
    lowered = text.lower()
    if any(w in lowered for w in _NEG):
        return -1
    if any(w in lowered for w in _POS):
        return 1
    return 0
