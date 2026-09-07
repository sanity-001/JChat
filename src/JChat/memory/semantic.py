"""语义向量索引（借鉴 Alife：bge-small-zh + 余弦检索的 JChat 适配版）。

- 模型：BAAI/bge-small-zh-v1.5，经 fastembed（onnxruntime）本地推理，无 torch 依赖
- 可选依赖：未安装 fastembed 时 `available()` 返回 False，recall 退回纯词面检索
- 结构：增量维护 (memory_id → 向量) 矩阵，余弦 top-k
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger("JChat.semantic")

_MODEL = "BAAI/bge-small-zh-v1.5"


class SemanticMemoryIndex:
    def __init__(self) -> None:
        self._model = None
        self._ids: list[str] = []
        self._matrix: np.ndarray | None = None
        self._failed = False  # 依赖缺失时不再反复尝试

    def available(self) -> bool:
        if self._model is not None:
            return True
        if self._failed:
            return False
        try:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(_MODEL)
            logger.info("语义检索已启用：%s", _MODEL)
            return True
        except Exception as e:  # noqa: BLE001 - 依赖缺失/模型下载失败均降级
            logger.info("语义检索不可用（退回词面检索）：%s", e)
            self._failed = True
            return False

    def rebuild(self, items: list[tuple[str, str]]) -> None:
        """全量重建：items = [(memory_id, content)]。"""
        if not self.available() or not items:
            self._ids, self._matrix = [], None
            return
        self._ids = [mid for mid, _ in items]
        vecs = np.array(list(self._model.embed([t for _, t in items])), dtype=np.float32)
        norm = np.linalg.norm(vecs, axis=1, keepdims=True)
        norm[norm == 0] = 1
        self._matrix = vecs / norm

    def top(self, query: str, k: int = 5) -> list[tuple[str, float]]:
        """返回 [(memory_id, cosine)]，余弦降序。"""
        if self._matrix is None or not len(self._ids):
            return []
        q = np.array(list(self._model.embed([query]))[0], dtype=np.float32)
        qn = np.linalg.norm(q)
        if qn:
            q = q / qn
        cos = self._matrix @ q
        idx = np.argsort(-cos)[:k]
        return [(self._ids[i], float(cos[i])) for i in idx]

    def upsert(self, memory_id: str, content: str) -> None:
        """增量追加（remember 后调用，避免全量重算）。"""
        if not self.available():
            return
        try:
            vec = np.array(list(self._model.embed([content]))[0], dtype=np.float32)
        except Exception as e:  # noqa: BLE001
            logger.warning("单条向量化失败：%s", e)
            return
        norm = np.linalg.norm(vec)
        if norm:
            vec = vec / norm
        self._ids.append(memory_id)
        if self._matrix is None:
            self._matrix = vec[None, :]
        else:
            self._matrix = np.vstack([self._matrix, vec])
