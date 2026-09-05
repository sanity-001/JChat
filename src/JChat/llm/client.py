"""LLM 客户端（票据 007/001）：OpenAI 兼容、非流式（票据 014 决策 Q14 B）、function calling。"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("JChat.llm")


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
        http_client = None
        if llm.get("proxy"):
            http_client = httpx.Client(proxies={"http://": llm["proxy"], "https://": llm["proxy"]})
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
                return resp.model_dump()
            except Exception as e:  # noqa: BLE001 - 交给循环层决定
                last_err = e
                logger.warning("LLM 调用失败（%s/%s）：%s", attempt + 1, self.max_retry + 1, e)
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"LLM 调用失败（已重试 {self.max_retry} 次）：{last_err}")

    def complete(self, messages: list[dict], max_tokens: int = 128) -> str:
        """轻量补全（主动搭话等），非工具调用。"""
        resp = self.chat(messages, max_tokens=max_tokens)
        return resp["choices"][0]["message"]["content"] or ""


def message(role: str, content: str) -> dict:
    return {"role": role, "content": content}
