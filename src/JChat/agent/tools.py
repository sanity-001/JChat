"""工具注册表与执行（票据 008）：run_python / read_file / write_file / list_files / web_fetch / remember。

边界（票据 008）：
- run_python：固定 working_dir，网络/包自由，60s 超时（kill），输出+stderr 合并截断 16KB
- 文件工具：全盘自由，write 记日志
- web_fetch：15s / 1MB / 仅 http(s)，返回剥标签纯文本
- remember：importance 可选默认 3，不受抽取阈值限制
- 回灌格式：成功 `[工具名] <输出>`（超限标记）；失败 `[工具名] [Error] <类型: 消息>`
"""

from __future__ import annotations

import html
import logging
import os
import re
import subprocess
from pathlib import Path

import requests

logger = logging.getLogger("JChat.tools")


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…[输出已截断，显示前 {limit} 字节]"


def _ok(name: str, output: str) -> str:
    return f"[{name}] {output}"


def _err(name: str, msg: str) -> str:
    return f"[{name}] [Error] {msg}"


# ------------------------------------------------------------------ registry
# 开源接缝①（docs/system.md §6）：新工具只需在函数上挂 @tool() 装饰器，
# schema 与执行自动注册，loop/app 无需改动。
_TOOL_REGISTRY: dict[str, dict] = {}


def tool(description: str, params: dict, required: list[str] | None = None):
    """把工具函数注册进注册表。handler 签名约定：(**args, ctx)。"""

    def deco(fn):
        _TOOL_REGISTRY[fn.__name__] = {
            "schema": {
                "type": "function",
                "function": {
                    "name": fn.__name__,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": params,
                        "required": required or [],
                    },
                },
            },
            "handler": fn,
        }
        return fn

    return deco


def tool_schemas() -> list[dict]:
    return [entry["schema"] for entry in _TOOL_REGISTRY.values()]


def execute(name: str, args: dict, ctx: dict) -> str:
    cancel = ctx.get("cancel")
    if cancel is not None and cancel.is_set():
        return _err(name, "cancelled")
    entry = _TOOL_REGISTRY.get(name)
    if entry is None:
        return _err(name, f"unknown tool {name}")
    try:
        return entry["handler"](**args, ctx=ctx)
    except TypeError as e:
        return _err(name, f"bad arguments: {e}")
    except Exception as e:  # noqa: BLE001
        return _err(name, f"{type(e).__name__}: {e}")


@tool(
    "在本地执行一段 Python 代码（工作目录为配置的 working_dir，可访问网络与文件系统）。"
    "返回 stdout/stderr。",
    params={"code": {"type": "string"}},
    required=["code"],
)
def run_python(code: str, ctx: dict) -> str:
    cfg = ctx["config"]
    tcfg = cfg["tools"]
    timeout = tcfg["run_timeout"]
    limit = tcfg["output_limit_bytes"]
    cwd = tcfg["working_dir"]
    proc = subprocess.Popen(
        [os.sys.executable, "-c", code],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    cancel = ctx.get("cancel")
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        return _err("run_python", f"Timeout after {timeout}s")
    if cancel is not None and cancel.is_set():
        proc.kill()
        return _err("run_python", "已取消")
    output = (out or "") + (("\n--- stderr ---\n" + err) if err else "")
    if proc.returncode != 0:
        return _err("run_python", f"exit code {proc.returncode}: {_clip(output, limit)}")
    return _ok("run_python", _clip(output, limit))


@tool("读取本地文件内容（文本，支持任意路径）。", params={"path": {"type": "string"}}, required=["path"])
def read_file(path: str, ctx: dict) -> str:
    p = Path(path)
    if not p.is_file():
        return _err("read_file", f"not a file: {path}")
    limit = ctx["config"]["tools"]["output_limit_bytes"]
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return _err("read_file", str(e))
    return _ok("read_file", _clip(text, limit))


@tool(
    "写入本地文件（自动创建父目录，UTF-8）。",
    params={"path": {"type": "string"}, "content": {"type": "string"}},
    required=["path", "content"],
)
def write_file(path: str, content: str, ctx: dict) -> str:
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except OSError as e:
        return _err("write_file", str(e))
    logger.info("write_file -> %s (%d bytes)", p, len(content))
    return _ok("write_file", f"written {len(content)} bytes to {path}")


@tool("列出目录内容（递归请多次调用）。", params={"path": {"type": "string"}}, required=["path"])
def list_files(path: str, ctx: dict) -> str:
    p = Path(path)
    if not p.is_dir():
        return _err("list_files", f"not a directory: {path}")
    limit = ctx["config"]["tools"]["output_limit_bytes"]
    try:
        entries = []
        for child in sorted(p.iterdir()):
            entries.append(f"{'[D]' if child.is_dir() else '[F]'} {child.name}")
        return _ok("list_files", _clip("\n".join(entries), limit))
    except OSError as e:
        return _err("list_files", str(e))


_TAG_RE = re.compile(r"<[^>]+>")


@tool(
    "抓取网页并返回纯文本（仅 http/https，上限 1MB）。",
    params={"url": {"type": "string"}},
    required=["url"],
)
def web_fetch(url: str, ctx: dict) -> str:
    tcfg = ctx["config"]["tools"]
    if not url.lower().startswith(("http://", "https://")):
        return _err("web_fetch", "only http/https allowed")
    try:
        resp = requests.get(
            url,
            timeout=tcfg["web_fetch_timeout"],
            stream=True,
            headers={"User-Agent": "JChat/0.1"},
        )
        resp.raise_for_status()
        data = resp.raw.read(tcfg["web_fetch_max_bytes"] + 1, decode_content=True)
        if len(data) > tcfg["web_fetch_max_bytes"]:
            return _err("web_fetch", f"response exceeds {tcfg['web_fetch_max_bytes']} bytes")
        text = html.unescape(_TAG_RE.sub(" ", data.decode("utf-8", errors="replace")))
        text = re.sub(r"\s+", " ", text).strip()
        return _ok("web_fetch", _clip(text, tcfg["output_limit_bytes"]))
    except Exception as e:  # noqa: BLE001
        return _err("web_fetch", f"{type(e).__name__}: {e}")


@tool(
    "把一条关于用户的事实写入长期记忆（重要度 1-10，默认 3）。",
    params={
        "content": {"type": "string"},
        "entity_names": {
            "type": "array",
            "items": {"type": "string"},
            "description": "可关联的知识库实体名",
        },
        "importance": {"type": "number"},
    },
    required=["content"],
)
def remember(content: str, ctx: dict, entity_names: list[str] | None = None, importance: float = 3.0) -> str:
    memory = ctx["memory"]
    if not content or not content.strip():
        return _err("remember", "content required")
    memory_id = memory.remember(content=content, entity_names=entity_names, importance=float(importance))
    return _ok("remember", f"saved ({memory_id[:8]}…)")


@tool(
    "主动检索长期记忆与知识图谱。当用户提到过去的事、你记忆卡里没有相关内容、或想不起细节时使用。",
    params={
        "query": {"type": "string", "description": "检索关键词或问题"},
        "k": {"type": "integer", "description": "返回条数上限，默认 5"},
    },
    required=["query"],
)
def recall(query: str, ctx: dict, k: int = 5) -> str:
    from JChat.agent.prompts import rel_time

    memory = ctx["memory"]
    retriever = ctx.get("retriever")
    if not query or not query.strip():
        return _err("recall", "query required")
    lines: list[str] = []
    for m in memory.recall(query.strip(), k=max(1, int(k))):
        lines.append(f"- [{rel_time(m['created_at'])}] {m['content']}")
    if retriever is not None:
        names: set[str] = set()
        for ent in retriever.entity_link(query.strip()):
            names.add(ent["name"])
        for hit in retriever.graph_search(query.strip(), depth=2, k=20):
            names.add(hit.name)
        for r in retriever._triples_for(names, 6):
            lines.append(f"- {r['head_name']} --{r['rel_type']}--> {r['tail_name']}")
    if not lines:
        return _ok("recall", "（记忆中没有找到相关内容）")
    return _ok("recall", "\n".join(lines))


