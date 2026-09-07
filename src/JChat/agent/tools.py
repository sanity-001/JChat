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


@tool(
    "查询当前可见窗口列表（含窗口句柄 hwnd 与焦点状态）。",
    params={},
)
def query_windows(ctx: dict) -> str:
    from JChat.agent.vision import list_windows

    wins = [w for w in list_windows() if w["title"]]
    lines = []
    for w in wins:
        mark = " | 【当前焦点】" if w["focused"] else ""
        lines.append(f"hwnd: {w['hwnd']} | 标题: {w['title']}{mark}")
    if not lines:
        return _ok("query_windows", "（没有可见窗口）")
    lines.append("提示：把 hwnd 传给 see_screen 可以直接看这个窗口的画面")
    return _ok("query_windows", "\n".join(lines))


@tool(
    "看一眼屏幕：截图（全屏或指定 hwnd 的窗口）并用视觉模型分析画面内容。"
    "想知道用户在做什么、陪着吐槽、帮忙排查界面问题时使用。",
    params={
        "hwnd": {"type": "integer", "description": "窗口句柄；-1 表示全屏（可先用 query_windows 查）"},
        "prompt": {"type": "string", "description": "想从画面里知道什么"},
    },
)
def see_screen(ctx: dict, hwnd: int = -1, prompt: str = "用两三句话描述画面主要内容") -> str:
    from JChat.agent.vision import analyse, capture, list_windows

    fg = next((w["title"] for w in list_windows() if w["focused"]), "未知")
    prompt = f"{prompt}\n（当前用户焦点窗口：{fg}）"
    path = capture(None if int(hwnd) < 0 else int(hwnd))
    result = analyse(path, prompt, ctx["llm"])
    return _ok("see_screen", f"画面分析：{result}")


@tool(
    "联网搜索（DuckDuckGo），返回前几条结果的标题/链接/摘要。",
    params={
        "query": {"type": "string"},
        "k": {"type": "integer", "description": "条数上限，默认 5"},
    },
    required=["query"],
)
def web_search(query: str, ctx: dict, k: int = 5) -> str:
    import re
    from urllib.parse import parse_qs, unquote, urlparse

    import requests

    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    lines: list[str] = []

    def _clean(s: str) -> str:
        return re.sub(r"<[^>]+>", "", s).strip()

    def _real_url(href: str) -> str:
        if href.startswith("//duckduckgo.com/l/") or "uddg=" in href:
            q = parse_qs(urlparse(href).query)
            return unquote(q.get("uddg", [href])[0])
        return href

    # 引擎回退链：DDG → Bing（国内网络可达性）
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/", params={"q": query}, timeout=15, headers=ua
        )
        resp.raise_for_status()
        text = resp.text
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', text, re.S)
        hrefs = re.findall(r'class="result__a"[^>]*href="([^"]+)"', text)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', text, re.S)
        for i in range(min(len(titles), max(1, int(k)))):
            url = _real_url(hrefs[i]) if i < len(hrefs) else ""
            snippet = _clean(snippets[i]) if i < len(snippets) else ""
            lines.append(f"{i + 1}. {_clean(titles[i])}\n   {url}\n   {snippet}")
    except Exception as e:  # noqa: BLE001
        logger.info("DDG 搜索失败，回退 Bing：%s", e)

    if not lines:
        try:
            resp = requests.get(
                "https://www.bing.com/search", params={"q": query, "mkt": "zh-CN"},
                timeout=15, headers=ua,
            )
            resp.raise_for_status()
            blocks = re.findall(r'<li class="b_algo".*?</li>', resp.text, re.S)
            for i, block in enumerate(blocks[: max(1, int(k))]):
                m_url = re.search(r'<h2[^>]*><a[^>]*href="([^"]+)"', block)
                m_title = re.search(r'<h2[^>]*><a[^>]*>(.*?)</a>', block, re.S)
                m_snip = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
                if not m_title:
                    continue
                lines.append(
                    f"{i + 1}. {_clean(m_title.group(1))}\n"
                    f"   {m_url.group(1) if m_url else ''}\n"
                    f"   {_clean(m_snip.group(1)) if m_snip else ''}"
                )
        except Exception as e:  # noqa: BLE001
            return _err("web_search", f"DDG 与 Bing 均失败：{type(e).__name__}: {e}")

    if not lines:
        return _err("web_search", "没有解析到结果")
    return _ok("web_search", "\n".join(lines))


@tool(
    "创建一个定时报点（ISO-8601，如 2026-09-07T22:30:00）。到点你会被唤醒并向用户主动说话。"
    "用于早晚问候、提醒自己、记住用户提到的时间并守约。",
    params={
        "time": {"type": "string", "description": "ISO-8601 本地时间"},
        "remark": {"type": "string", "description": "到点时提醒自己的话"},
    },
    required=["time"],
)
def schedule(time: str, ctx: dict, remark: str = "") -> str:
    cb = ctx.get("scheduler")
    if not cb:
        return _err("schedule", "scheduler unavailable")
    return cb(time, remark)


@tool(
    "打开游戏窗口，陪用户一起玩。当用户说想玩游戏/下棋/来一局时使用。",
    params={
        "game": {"type": "string", "description": "游戏名，当前支持：五子棋"},
    },
)
def play_game(ctx: dict, game: str = "五子棋") -> str:
    cb = ctx.get("open_game")
    if not cb:
        return _err("play_game", "unavailable")
    return cb(game)


