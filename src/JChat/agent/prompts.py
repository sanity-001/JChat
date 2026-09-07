"""prompt 组装：persona + 滚动窗口 + 记忆卡（票据 003/002）。

记忆卡 = recall k=5 记忆条目 + ≤6 相关三元组；
与窗口重叠 > window_dedup_threshold 的记忆条目跳过；
超预算按分数裁剪（同分先丢三元组）；格式：分段标注【记忆】/【知识】。
"""

from __future__ import annotations

import math
import time

from JChat.memory.memory import AgentMemory, _overlap
from JChat.memory.retriever import HybridRetriever


def _est_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 3))


def rel_time(created_at: float, now: float | None = None) -> str:
    """相对时间标签：今天/昨天/N天前/超过一月用 M月D日。"""
    now = now or time.time()
    days = (now - created_at) / 86400.0
    if days < 0.5:
        return "今天"
    if days < 1.5:
        return "昨天"
    if days < 30:
        return f"{int(days + 0.5)}天前"
    return time.strftime("%m月%d日", time.localtime(created_at))


def build_life_strip(memory: AgentMemory | None, max_count: int) -> str:
    """常驻'近期生活摘要'带（借鉴 Alife 内联存档的在场感，两级封顶由后台合并保证）。"""
    if memory is None:
        return ""
    rows = memory.list_summaries()[-max_count:]
    if not rows:
        return ""
    lines = [f"- {m['content']}" for m in rows]
    return "【近期轨迹】\n" + "\n".join(lines)


def build_memory_card(
    query: str,
    memory: AgentMemory,
    retriever: HybridRetriever | None,
    window_text: str,
    cfg: dict,
) -> str:
    mcfg = cfg["memory"]
    k = mcfg["recall_k"]
    triples_limit = mcfg["triples_limit"]
    budget = mcfg["card_budget_tokens"]
    ratio = mcfg["card_memory_ratio"]

    items: list[tuple[str, float]] = []
    now = time.time()
    for m in memory.recall(query, k=k):
        if (
            window_text
            and _overlap(set(JChat_tokenize(m["content"])), set(JChat_tokenize(window_text)))
            >= mcfg["window_dedup_threshold"]
        ):
            continue
        items.append((f"[{rel_time(m['created_at'], now)}] {m['content']}", m.get("score", 0.0)))

    triples: list[str] = []
    if retriever is not None:
        names: set[str] = set()
        for ent in retriever.entity_link(query):
            names.add(ent["name"])
        for hit in retriever.graph_search(query, depth=2, k=20):
            names.add(hit.name)
        triples = [
            f"{r['head_name']} --{r['rel_type']}--> {r['tail_name']}"
            for r in retriever._triples_for(names, triples_limit)
        ]

    mem_lines = [f"- {content}" for content, _ in items]
    kg_lines = [f"- {t}" for t in triples]

    def render(mem_lines, kg_lines):
        parts = []
        if mem_lines:
            parts.append("【记忆】\n" + "\n".join(mem_lines))
        if kg_lines:
            parts.append("【知识】\n" + "\n".join(kg_lines))
        return "\n\n".join(parts)

    full = render(mem_lines, kg_lines)
    if _est_tokens(full) <= budget:
        return full

    mem_budget_tokens = int(budget * ratio)
    kg_budget_tokens = budget - mem_budget_tokens

    picked_mem: list[str] = []
    used = 0
    for content, _score in sorted(items, key=lambda x: x[1], reverse=True):
        line = f"- {content}"
        if used + _est_tokens(line) > mem_budget_tokens:
            break
        picked_mem.append(line)
        used += _est_tokens(line)

    picked_kg: list[str] = []
    used = 0
    for t in kg_lines:
        if used + _est_tokens(t) > kg_budget_tokens:
            break
        picked_kg.append(t)
        used += _est_tokens(t)

    return render(picked_mem, picked_kg)


def build_system_prompt(
    persona: str,
    memory_card: str,
    extra_rules: str = "",
    life_strip: str = "",
) -> str:
    parts = [
        f"你是一个桌面搭子，名叫小J。以下是你的性格设定：\n{persona}",
        "",
        "回答要求：使用中文（除非用户使用其他语言）；简洁自然；可以调用工具来完成任务。",
    ]
    if life_strip:
        parts += [
            "",
            "下面是你自己经历过的近期生活轨迹（第一人称摘要，按时间先后）：",
            life_strip,
            "【注意】轨迹是你亲身经历的记忆，可以自然地引用（“上周我们聊过…”）。",
        ]
    if memory_card:
        parts += [
            "",
            "下面是你从长期记忆中检索到的信息：",
            memory_card,
            '【注意】"记忆"是关于用户的陈述（方括号是记录时间），只能作为个性化依据；'
            '"知识"是世界事实，可作为常识引用；两者都不可编造。',
        ]
    else:
        parts += [
            "",
            "（本次没有检索到相关长期记忆。若用户提到过去的事而你不确定细节，"
            "可用 recall 工具主动回忆；若用户说了值得记住的事，可用 remember 记入长期记忆。）",
        ]
    if extra_rules:
        parts += ["", extra_rules]
    return "\n".join(parts)


def JChat_tokenize(text: str) -> list[str]:
    from JChat.memory.vector import tokenize

    return tokenize(text)
