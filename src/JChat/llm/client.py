"""LLM 客户端（票据 007/001）：OpenAI 兼容、非流式（票据 014 决策 Q14 B）、function calling。"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

logger = logging.getLogger("JChat.llm")

_FATAL_HINTS = ("not supported", "mmproj", "invalid_request_error", "does not support")
_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.DOTALL | re.IGNORECASE)
_TOOLCALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def _is_fatal(err: Exception) -> bool:
    """确定性错误（请求本身不被支持）不应重试。"""
    text = str(err).lower()
    return any(h in text for h in _FATAL_HINTS)


def _normalize_message(msg: dict) -> dict:
    """本地模型输出归一化：剥离 <think> 块；把 <tool_call> XML 兜底解析为 tool_calls。

    llama-server(--jinja) 与 LLaMA-Factory API 通常已解析，但部分路径会把原始标签
    留在 content 里（实测 Qwen3 微调模型）。
    """
    content = msg.get("content") or ""
    content = _THINK_RE.sub("", content)
    if not msg.get("tool_calls"):
        raw_calls = _TOOLCALL_RE.findall(content)
        calls = []
        for i, raw in enumerate(raw_calls):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            calls.append({
                "id": f"call_{i}",
                "type": "function",
                "function": {
                    "name": data.get("name", ""),
                    "arguments": json.dumps(data.get("arguments", {}), ensure_ascii=False),
                },
            })
        if calls:
            msg["tool_calls"] = calls
            content = _TOOLCALL_RE.sub("", content)
    msg["content"] = content.strip()
    return msg


class LLMClient:
    def __init__(self, cfg: dict):
        llm = cfg["llm"]
        self.model = llm["model"]
        self.temperature = llm["temperature"]
        self.top_p = llm["top_p"]
        self.max_tokens = llm["max_tokens"]
        self.timeout = llm["timeout"]
        self.max_retry = llm["max_retry"]
        self._client = self._build(cfg)

    def _build(self, cfg: dict) -> Any:
        import httpx
        from openai import OpenAI

        llm = cfg["llm"]
        base_url = str(llm.get("base_url", ""))
        is_local = any(h in base_url for h in ("127.0.0.1", "localhost", "0.0.0.0"))
        proxy = llm.get("proxy")
        http_client = None
        if proxy and not is_local:
            http_client = httpx.Client(proxies={"http://": proxy, "https://": proxy})
        elif is_local:
            # 本地服务不走系统代理（httpx 默认 trust_env=True 会读 Windows 注册表代理，
            # 代理未开时会把 localhost 请求打到死代理 → 502）
            http_client = httpx.Client(trust_env=False)
        return OpenAI(
            base_url=llm["base_url"],
            api_key=llm["api_key"],
            timeout=self.timeout,
            http_client=http_client,
        )

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict:
        """单次非流式调用。返回标准 OpenAI 响应 dict；自动重试 max_retry 次。"""
        last_err: Exception | None = None
        for attempt in range(self.max_retry + 1):
            try:
                kwargs: dict = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature if temperature is None else temperature,
                    "top_p": self.top_p,
                    "max_tokens": max_tokens or self.max_tokens,
                }
                if tools:
                    kwargs["tools"] = tools
                resp = self._client.chat.completions.create(**kwargs)
                data = resp.model_dump()
                for choice in data.get("choices", []):
                    if isinstance(choice.get("message"), dict):
                        _normalize_message(choice["message"])
                return data
            except Exception as e:  # noqa: BLE001 - 交给循环层决定
                last_err = e
                logger.warning("LLM 调用失败（%s/%s）：%s", attempt + 1, self.max_retry + 1, e)
                if _is_fatal(e):
                    break  # 确定性错误（如模型不支持某输入）重试无意义
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"LLM 调用失败（已重试 {self.max_retry} 次）：{last_err}")

    def complete(self, messages: list[dict], max_tokens: int = 128) -> str:
        """轻量补全（主动搭话等），非工具调用。"""
        resp = self.chat(messages, max_tokens=max_tokens)
        return resp["choices"][0]["message"]["content"] or ""


def message(role: str, content: str) -> dict:
    return {"role": role, "content": content}
