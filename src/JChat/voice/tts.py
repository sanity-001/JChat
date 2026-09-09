"""发声（TTS）：文本预处理 + 双 provider（GPT-SoVITS 零样本克隆 / EdgeTTS 兜底）。

- GPT-SoVITS：调用其 api_v2 HTTP 服务（默认 http://127.0.0.1:9880/tts），
  零样本模式传参考音频路径 + prompt 文本，无需训练
- EdgeTTS：微软在线神经音色（兜底），需 edge-tts 包
"""

from __future__ import annotations

import logging
import os
import re
import tempfile

import requests

logger = logging.getLogger("JChat.voice.tts")

_MAX_TTS_CHARS = 300
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\u2190-\u21FF\u2B00-\u2BFF]"
)


def tts_text(text: str) -> str:
    """回复 → 可朗读文本：剥 markdown/emoji，代码块替换提示，超长截断。"""
    text = re.sub(r"```[\s\S]*?```", "代码部分请看文字。", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # 链接只读文字
    text = re.sub(r"^#{1,4}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_~>]+", "", text)
    text = re.sub(r"^[-*]\s+", "", text, flags=re.MULTILINE)
    text = _EMOJI.sub("", text)
    text = re.sub(r"\n{2,}", "。", text).replace("\n", "，").strip()
    if len(text) > _MAX_TTS_CHARS:
        text = text[:_MAX_TTS_CHARS] + "……后面太长，看文字吧。"
    return text


def _unique_path(ext: str) -> str:
    """唯一临时文件名：QMediaPlayer 可能仍占用上一个文件（Permission denied 根因）。"""
    import time

    return os.path.join(tempfile.gettempdir(), f"jchat_tts_{int(time.time() * 1000)}.{ext}")


def speak_gptsovits(
    text: str,
    base_url: str,
    ref_audio: str,
    ref_text: str,
    timeout: float = 60.0,
) -> str:
    """GPT-SoVITS api_v2 零样本克隆，返回 wav 临时文件路径。失败抛异常。"""
    resp = requests.get(
        f"{base_url.rstrip('/')}/tts",
        params={
            "text": text,
            "text_language": "zh",
            "refer_wav_path": ref_audio,
            "prompt_text": ref_text,
            "prompt_language": "zh",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    path = _unique_path("wav")
    with open(path, "wb") as fh:
        fh.write(resp.content)
    return path


def speak_edge(text: str, voice: str = "zh-CN-XiaoyiNeural", rate: str = "+10%") -> str:
    """EdgeTTS 兜底，返回 mp3 临时文件路径。失败抛异常。"""
    import asyncio

    import edge_tts

    async def _run() -> bytes:
        com = edge_tts.Communicate(text, voice, rate=rate)
        buf = bytearray()
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        return bytes(buf)

    data = asyncio.run(_run())
    path = _unique_path("mp3")
    with open(path, "wb") as fh:
        fh.write(data)
    return path
