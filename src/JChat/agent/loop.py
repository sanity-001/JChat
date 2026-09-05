"""Agent 循环（票据 008 循环、Q8）：标准 tool-calling 循环，上限 max_iterations，支持取消。"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from JChat.agent import tools as tool_mod
from JChat.agent.prompts import build_memory_card, build_system_prompt
from JChat.llm.client import LLMClient, message


@dataclass
class ToolEvent:
    name: str
    args_preview: str = ""
    status: str = "running"
    output_preview: str = ""
    elapsed: float = 0.0


@dataclass
class AgentContext:
    config: dict
    llm: LLMClient
    memory: object
    retriever: object | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    on_tool_event: Callable[[ToolEvent], None] | None = None


def build_turn_messages(
    persona: str, window: list[dict], user_text: str, ctx: AgentContext, proactive_text: str | None = None
) -> tuple[list[dict], str]:
    """组装本轮 messages：system(persona+记忆卡) + 窗口 + (主动搭话上下文) + 当前用户消息。"""
    window_text = " ".join(
        f"{m['role']}: {m['content']}" for m in window[-ctx.config["memory"]["window_turns"] * 2 :]
    )
    memory_card = build_memory_card(user_text, ctx.memory, ctx.retriever, window_text, ctx.config)
    system = build_system_prompt(ctx.config["companion"]["persona"], memory_card)
    messages: list[dict] = [message("system", system)]
    for m in window:
        messages.append(message(m["role"], m["content"]))
    if proactive_text:
        messages.append(message("assistant", f"（你刚才主动对用户说：{proactive_text}）"))
    messages.append(message("user", user_text))
    return messages, memory_card


def run_turn(
    user_text: str, window: list[dict], ctx: AgentContext, proactive_text: str | None = None
) -> tuple[str, list[ToolEvent]]:
    """执行一轮对话（tool-calling 循环）。返回 (最终回复, 工具事件列表)。"""
    messages, _card = build_turn_messages(
        ctx.config["companion"]["persona"], window, user_text, ctx, proactive_text
    )
    events: list[ToolEvent] = []
    max_iter = ctx.config["agent"]["max_iterations"]
    schemas = tool_mod.tool_schemas()

    for _ in range(max_iter):
        if ctx.cancel.is_set():
            return "（已停止）", events
        resp = ctx.llm.chat(messages, tools=schemas)
        msg = resp["choices"][0]["message"]
        if not msg.get("tool_calls"):
            return msg.get("content") or "", events

        messages.append(
            {
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": msg["tool_calls"],
            }
        )
        for tc in msg["tool_calls"]:
            if ctx.cancel.is_set():
                return "（已停止）", events
            fn = tc["function"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            event = ToolEvent(
                name=fn["name"],
                args_preview=json.dumps(args, ensure_ascii=False)[:120],
            )
            if ctx.on_tool_event:
                ctx.on_tool_event(event)
            result = tool_mod.execute(fn["name"], args, ctx)
            event.status = "done" if not result.startswith(f"[{fn['name']}] [Error]") else "error"
            event.output_preview = result[:200]
            events.append(event)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
    return "（已达到工具调用上限，请重新提问或简化任务）", events
