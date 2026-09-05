"""冒烟测试：配置、记忆、知识图谱、记忆卡、工具（无 Qt / 无网络 / 无 LLM key）。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from JChat.agent.prompts import build_memory_card
from JChat.agent.tools import execute
from JChat.config import ensure_default_configs, load_config
from JChat.memory.builder import KnowledgeGraphBuilder
from JChat.memory.memory import AgentMemory
from JChat.memory.ontology import default_tech
from JChat.memory.retriever import HybridRetriever
from JChat.memory.storage import SQLiteStore
from JChat.memory.vector import build_vector_index


def test_config_defaults():
    ensure_default_configs()
    cfg = load_config()
    assert cfg["llm"]["base_url"] == "https://api.deepseek.com"
    assert cfg["agent"]["max_iterations"] == 5
    assert cfg["memory"]["recall_k"] == 5


def test_memory_lifecycle():
    store = SQLiteStore(":memory:")
    memory = AgentMemory(store, working_window=10, decay_rate=0.01)
    memory.remember("用户偏好向量数据库", ["VectorDatabase"], importance=5.0)
    memory.remember("用户做过 RAG 项目", ["RAG"], importance=3.0)
    hits = memory.recall("向量数据库 偏好", k=5)
    assert any("向量数据库" in h["content"] for h in hits)
    result = memory.consolidate()
    assert result["promoted"] >= 1
    assert memory.check_contradictions() is not None


def test_graph_build_and_hybrid():
    store = SQLiteStore(":memory:")
    builder = KnowledgeGraphBuilder(ontology=default_tech(), store=store)
    with tempfile.TemporaryDirectory() as tmp:
        doc = Path(tmp) / "rag.md"
        doc.write_text(
            "LangChain is a framework for building RAG applications. "
            "Vector databases are used in RAG. RAG outperforms plain search.",
            encoding="utf-8",
        )
        kg = builder.build_from_documents([doc])
        assert kg.graph.number_of_nodes() > 0
        retriever = HybridRetriever(kg, build_vector_index(store.all_doc_texts()))
        hits = retriever.hybrid_search("which library is used in RAG?", k=3)
        assert len(hits) >= 1
        assert "LangChain" in retriever.context(hits, top=1)


def test_memory_card_assembly():
    store = SQLiteStore(":memory:")
    memory = AgentMemory(store)
    memory.remember("用户偏好向量数据库", importance=5.0)
    memory.remember("用户讨厌拖延", importance=4.0)
    card = build_memory_card(
        "向量数据库 偏好",
        memory,
        None,
        "",
        {
            "memory": {
                "recall_k": 5,
                "triples_limit": 6,
                "card_budget_tokens": 800,
                "card_memory_ratio": 0.6,
                "window_dedup_threshold": 0.6,
                "memory_dedup_threshold": 0.85,
            },
        },
    )
    assert "【记忆】" in card
    assert "向量数据库" in card


def test_tools():
    ctx = {
        "config": {
            "tools": {
                "working_dir": str(Path.cwd()),
                "run_timeout": 30,
                "output_limit_bytes": 4096,
                "web_fetch_timeout": 10,
                "web_fetch_max_bytes": 1024,
            }
        }
    }
    out = execute("run_python", {"code": "print(6*7)"}, ctx)
    assert "42" in out
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "a" / "b.txt"
        assert execute("write_file", {"path": str(path), "content": "hello"}, ctx).startswith("[write_file]")
        assert "hello" in execute("read_file", {"path": str(path)}, ctx)
        listing = execute("list_files", {"path": str(Path(tmp) / "a")}, ctx)
        assert "b.txt" in listing


def test_extractor_no_key():
    from JChat.agent.extractor import extract_session

    store = SQLiteStore(":memory:")
    memory = AgentMemory(store)
    result = extract_session([{"role": "user", "content": "我喜欢向量数据库"}], memory, store, None)
    assert result is None
