"""会话后自动抽取（票据 005）：一次 LLM 调用返回 facts + triples 两数组。

- 用户陈述（importance≥3）→ 记忆（memory.remember，与旧记忆相似度≥0.85 判重只 touch）
- 通用概念关系 → 知识库（relations 表，chat doc_id 来源标记）
- 无 API key：对话抽取整体停用（返回 None），文档抽取仍可用 RuleExtractor
"""

from __future__ import annotations

import json
import logging
import re
import time

from JChat.memory.graph import node_id
from JChat.memory.memory import AgentMemory, _overlap
from JChat.memory.ontology import Ontology, default_tech
from JChat.memory.vector import tokenize

logger = logging.getLogger("JChat.extractor")

_SYSTEM = """你是用户的桌面搭子小J。你即将把一段刚发生的对话整理成长期记忆。
以你自己的第一人称视角、带感情但精简地提炼：关于用户的重要事实（偏好/经历/约定/情绪）、以及你了解到的世界知识。
只输出 JSON，不要任何解释。结构如下：
{
  "facts": [{"content": "以“用户…”开头的一句话事实（避免第一人称主语，方便日后检索）",
             "importance": 1-10, "entities": ["可关联的实体名（可选）"]}],
  "relations": [{"head": "实体名", "rel_type": "关系名", "tail": "实体名"}]
}
关系类型仅限：implements, based_on, outperforms, used_in, proposes。
只抽取对话中明确陈述的内容；琐碎寒暄不抽；facts 只抽关于用户的，relations 只抽世界知识。
宁可少而准，不要多而杂。"""

_USER = """对话记录：
{transcript}

返回 JSON。"""

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_session(
    transcript: list[dict],
    memory: AgentMemory,
    store,
    llm,
    ontology: Ontology | None = None,
    cfg: dict | None = None,
) -> dict | None:
    """从会话记录抽取记忆与三元组。无 key / 失败返回 None。"""
    if llm is None:
        return None
    mcfg = cfg["memory"] if cfg else {}
    threshold = float(mcfg.get("memory_dedup_threshold", 0.85))
    importance_floor = float(mcfg.get("importance_threshold", 3))
    ontology = ontology or default_tech()

    lines = [f"{m['role']}: {m['content']}" for m in transcript]
    transcript_text = "\n".join(lines)
    try:
        resp = llm.chat(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _USER.format(transcript=transcript_text[:24000])},
            ],
            max_tokens=2048,
        )
        raw = resp["choices"][0]["message"]["content"] or "{}"
        data = _parse_json(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("会话抽取失败：%s", e)
        return None

    saved_facts = 0
    for fact in data.get("facts", []):
        content = str(fact.get("content", "")).strip()
        if not content or len(content) < 6:
            continue
        importance = float(fact.get("importance", 0) or 0)
        if importance < importance_floor:
            continue
        existing = memory.recall(content, k=5)
        dup = False
        for old in existing:
            if _overlap(set(tokenize(old["content"])), set(tokenize(content))) >= threshold:
                dup = True
                break
        if dup:
            continue
        memory.remember(content=content, entity_names=fact.get("entities") or [], importance=importance)
        saved_facts += 1

    saved_triples = _save_triples(data.get("relations", []), store, transcript_text, ontology)
    return {"facts": saved_facts, "triples": saved_triples}


def _save_triples(relations: list, store, transcript_text: str, ontology: Ontology) -> int:
    if not relations:
        return 0
    valid_rel = set(ontology.relation_types)
    doc_id, _changed = store.upsert_doc(f"chat/{time.time()}", transcript_text)
    count = 0
    seen: set[tuple[str, str, str]] = set()
    for r in relations:
        head = str(r.get("head", "")).strip()
        tail = str(r.get("tail", "")).strip()
        rel = str(r.get("rel_type", "")).strip()
        if not head or not tail or rel not in valid_rel or head == tail:
            continue
        if (head, rel, tail) in seen:
            continue
        seen.add((head, rel, tail))
        store.save_node(node_id("Concept", head), "Concept", head, doc_id, 1.0)
        store.save_node(node_id("Concept", tail), "Concept", tail, doc_id, 1.0)
        store.save_relation(node_id("Concept", head), rel, node_id("Concept", tail), doc_id, 1.0)
        count += 1
    store.commit()
    return count


def _parse_json(raw: str) -> dict:
    cleaned = _FENCE.sub("", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise
