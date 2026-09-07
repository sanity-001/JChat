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


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

_SYSTEM = """你是用户的桌面搭子小J。你即将把一段刚发生的对话整理成长期记忆。
以你自己的第一人称视角、带感情但精简地提炼。
逐轮检查对话中的每个信息点，以下类型都要考虑（通常每段对话至少有 1-3 条）：
① 用户的身份信息（名字、职业、生日、所在地）
② 偏好与厌恶（喜欢/讨厌什么）
③ 用户身边的人、宠物、物品
④ 时间约定与日程（每周/每天什么时候做什么）
⑤ 用户在做的事与目标（项目、学习、计划）
⑥ 你了解到的世界知识

【重要】只记"长期有效"的事实，以下不属于记忆：
- 当日临时状态（今天吃了什么、今天累不累、当下心情、此刻在做的事）
- 一次性计划（今晚想吃什么、今天打算去哪）——除非用户明示"记住"

只输出 JSON，不要任何解释。结构如下：
{"facts": [{"content": "以“用户…”开头的一句话事实",
            "importance": 1-10, "entities": ["可关联的实体名（可选）"]}],
 "relations": [{"head": "实体名", "rel_type": "关系名", "tail": "实体名"}]}
关系类型仅限：implements, based_on, outperforms, used_in, proposes。
示例：
- 用户说"我叫小明" → {"content": "用户名叫小明", "importance": 9}
- 用户说"我讨厌香菜" → {"content": "用户讨厌吃香菜", "importance": 7}
- 用户说"我每周三加班到十点" → {"content": "用户每周三晚上加班到十点", "importance": 7}
- 用户说"今天中午吃了牛肉面" → 不抽（当日临时状态）
只抽取对话中明确陈述的内容；琐碎寒暄不抽；facts 只抽关于用户的，relations 只抽世界知识。
宁可少而准，不要多而杂。"""

_USER = """已有记忆（重要：与这些记忆讲同一件事的，即使措辞完全不同，也绝对不要重复输出）：
{existing}

对话记录：
{transcript}

返回 JSON。"""

_SUMMARY_SYSTEM = """你是用户的桌面搭子小J。一段刚过去的日子即将离开你的短期注意范围，
请以你自己的第一人称视角、带感情但精简（150字以内）地写一段这段时期的生活轨迹：
发生了什么事、用户的重要动向、你印象最深的时刻。按时间顺序叙述，不用分点。
不要加日期头（系统会加）。直接输出纯摘要内容。"""

_SUMMARY_MERGE_SYSTEM = """你是用户的桌面搭子小J。下面是两段更早期的、按时间先后排列的生活轨迹摘要。
请把它们合并成一段更精简（150字以内）的第一人称轨迹摘要：保留最重要的事件与用户动向，
舍弃细节。不要加日期头（系统会加）。直接输出纯摘要内容。"""

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
    # 现有记忆全量携带（≤100 条）：跨批次判重 + 措辞对齐；规模测试 58 条 ≈ 900 token 可接受
    all_mem = [m for m in memory.state() if m.get("scope") != "summary"][:100] if memory else []
    existing_txt = "\n".join(f"- {m['content']}" for m in all_mem) or "（暂无）"
    try:
        resp = llm.chat(
            [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": _USER.format(
                        existing=existing_txt, transcript=transcript_text[:24000]
                    ),
                },
            ],
            max_tokens=2048,
            temperature=0.1,  # 结构化抽取：低温降低方差
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
        fact_tokens = set(tokenize(content))
        existing_contents = [m["content"] for m in all_mem]
        dup = False
        for old in existing_contents:
            old_tokens = set(tokenize(old))
            # 双保险：字面重合（原有）或 token Jaccard（措辞漂移时兜底）
            if (
                _overlap(fact_tokens, old_tokens) >= threshold
                or _jaccard(fact_tokens, old_tokens) >= 0.4
            ):
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


def _chat(raw: str, llm, system: str) -> str:
    resp = llm.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": raw[:24000]},
        ],
        max_tokens=512,
        temperature=0.4,
    )
    return (resp["choices"][0]["message"]["content"] or "").strip()


def _range_label(start_ts: float, end_ts: float) -> str:
    s = time.strftime("%m月%d日", time.localtime(start_ts))
    e = time.strftime("%m月%d日", time.localtime(end_ts))
    return s if s == e else f"{s}-{e}"


def summarize_block(
    transcript: list[dict],
    memory: AgentMemory,
    llm,
) -> str | None:
    """把一段已滑出滚动窗口的对话压成一条常驻生活摘要（scope=summary）。

    借鉴 Alife：第一人称、带感情、带日期范围；原文已在 chats 表永久保存。
    失败返回 None（下次继续重试，原文不丢）。
    """
    if llm is None or not transcript:
        return None
    text = "\n".join(f"{m['role']}: {m['content']}" for m in transcript)
    try:
        summary = _chat(text, llm, _SUMMARY_SYSTEM)
    except Exception as e:  # noqa: BLE001
        logger.warning("生活摘要失败：%s", e)
        return None
    if len(summary) < 20:
        logger.warning("生活摘要过短，丢弃：%r", summary[:50])
        return None
    existing = memory.list_summaries()
    if existing and _overlap(
        set(tokenize(existing[-1]["content"])), set(tokenize(summary))
    ) >= 0.6:
        logger.info("生活摘要与上一条高度相似，跳过")
        return None
    label = _range_label(transcript[0]["created_at"], transcript[-1]["created_at"])
    content = f"[{label}] {summary}"
    memory.remember_summary(content)
    return content


def merge_old_summaries(memory: AgentMemory, llm, max_count: int) -> bool:
    """摘要超过 max_count 时，把最老两条合并成一条更粗的轨迹（两级封顶）。"""
    if llm is None:
        return False
    summaries = memory.list_summaries()
    if len(summaries) <= max_count:
        return False
    old1, old2 = summaries[0], summaries[1]
    try:
        merged = _chat(
            f"轨迹一：{old1['content']}\n\n轨迹二：{old2['content']}", llm, _SUMMARY_MERGE_SYSTEM
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("摘要合并失败：%s", e)
        return False
    if len(merged) < 20:
        return False
    memory.store.delete_memories([old1["memory_id"], old2["memory_id"]])
    memory.remember_summary(f"[更早期] {merged}")
    return True
