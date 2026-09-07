"""屏幕视觉感知（借鉴 Alife VisionService）：窗口枚举 + 截屏 + 多模态分析。

仅 Windows；截图经 JPEG 压缩（宽边 ≤1280）后以 data URI 发给视觉模型，
分析文本返回给 agent（Alife 模式：工具内部完成视觉理解，agent 只拿结论）。
"""

from __future__ import annotations

import base64
import ctypes
import io
import logging
import tempfile
import time
from pathlib import Path

logger = logging.getLogger("JChat.vision")

_MAX_WIDTH = 1280


def list_windows() -> list[dict]:
    """枚举可见且有标题的顶层窗口：hwnd/标题/是否焦点。"""
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    out: list[dict] = []
    fg = user32.GetForegroundWindow()
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            out.append({
                "hwnd": int(hwnd) & 0xFFFFFFFF,
                "title": buf.value.strip(),
                "focused": bool(hwnd == fg),
            })
        return True

    user32.EnumWindows(proc(_cb), 0)
    return out


def capture(hwnd: int | None = None) -> str:
    """全屏（hwnd=None）或指定窗口（按窗口矩形裁剪）截图，返回 PNG 路径。"""
    from PIL import ImageGrab

    bbox = None
    if hwnd:
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        user32 = ctypes.windll.user32
        rect = RECT()
        if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            raise OSError(f"GetWindowRect 失败（hwnd={hwnd}）")
        bbox = (rect.left, rect.top, rect.right, rect.bottom)
    img = ImageGrab.grab(bbox=bbox, all_screens=True)
    path = Path(tempfile.gettempdir()) / f"jchat_screen_{int(time.time() * 1000)}.png"
    img.save(path)
    return str(path)


def analyse(path: str, prompt: str, llm) -> str:
    """把图片发给视觉模型分析，返回分析文本。"""
    from PIL import Image

    img = Image.open(path)
    if img.width > _MAX_WIDTH:
        img = img.resize((_MAX_WIDTH, int(img.height * _MAX_WIDTH / img.width)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    resp = llm.chat(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }
        ],
        max_tokens=512,
    )
    return (resp["choices"][0]["message"]["content"] or "").strip()
