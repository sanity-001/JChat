"""轻量 Markdown → HTML（QTextBrowser 富文本子集），先转义再转换，防注入。

支持：标题(#~####)、粗体/斜体、行内代码、围栏代码块、无序/有序列表、
链接、引用块、分隔线。其余按段落渲染，换行保留。
"""

from __future__ import annotations

import html
import re

_FENCE = re.compile(r"^```(\w*)\s*$")


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def _inline(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)
    return text


def md_to_html(text: str, body_font: str = "") -> str:
    """渲染 Markdown。body_font 非空时作为正文字体（Qt font-family 列表）。"""
    src = _escape(text or "")
    lines = src.split("\n")
    out: list[str] = []
    i = 0
    in_code = False
    code_buf: list[str] = []
    code_lang = ""
    list_stack: list[str] = []  # 'ul' | 'ol'

    def close_list() -> None:
        while list_stack:
            out.append(f"</{list_stack.pop()}>")

    font_attr = f"font-family:'{body_font}';" if body_font else ""

    while i < len(lines):
        line = lines[i]

        # 围栏代码块
        m = _FENCE.match(line.strip())
        if m:
            if in_code:
                out.append(
                    "<div style=\"background-color:#FFF6C9;color:#6B5600;"
                    "font-family:Consolas,monospace;padding:6px 8px;\">"
                    + "<br>".join(code_buf)
                    + "</div>"
                )
                code_buf = []
                in_code = False
            else:
                close_list()
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        stripped = line.strip()

        # 标题
        hm = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if hm:
            close_list()
            level = len(hm.group(1))
            size = {1: 19, 2: 17, 3: 16, 4: 15}[level]
            out.append(
                f"<div style=\"font-size:{size}px;font-weight:bold;color:#9A6AB5;"
                f"{font_attr}margin-top:4px;\">{_inline(hm.group(2))}</div>"
            )
            i += 1
            continue

        # 分隔线
        if re.match(r"^(-{3,}|\*{3,})$", stripped):
            close_list()
            out.append("<div style=\"color:#E8B4C8;\">―――――</div>")
            i += 1
            continue

        # 引用
        if stripped.startswith(">"):
            close_list()
            out.append(
                "<div style=\"color:#8A7A90;border-left:3px solid #F5C6D9;"
                f"{font_attr}padding-left:8px;\">{_inline(stripped.lstrip('> ').strip())}</div>"
            )
            i += 1
            continue

        # 无序列表
        um = re.match(r"^[-*]\s+(.*)$", stripped)
        if um:
            if not list_stack or list_stack[-1] != "ul":
                close_list()
                list_stack.append("ul")
                out.append("<ul>")
            out.append(f"<li>{_inline(um.group(1))}</li>")
            i += 1
            continue

        # 有序列表
        om = re.match(r"^(\d+)[.、]\s+(.*)$", stripped)
        if om:
            if not list_stack or list_stack[-1] != "ol":
                close_list()
                list_stack.append("ol")
                out.append("<ol>")
            out.append(f"<li>{_inline(om.group(2))}</li>")
            i += 1
            continue

        close_list()

        # 段落（连续非空行合并，保留手动换行）
        if stripped == "":
            i += 1
            continue
        para = [stripped]
        while i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if (
                not nxt
                or _FENCE.match(nxt)
                or nxt.startswith(("#", ">", "- ", "* "))
                or re.match(r"^\d+[.、]\s", nxt)
            ):
                break
            para.append(nxt)
            i += 1
        out.append(f"<div style=\"{font_attr}\">{_inline('<br>'.join(para))}</div>")
        i += 1

    if in_code:
        out.append(
            "<div style=\"background-color:#FFF6C9;color:#6B5600;"
            "font-family:Consolas,monospace;padding:6px 8px;\">"
            + "<br>".join(code_buf)
            + "</div>"
        )
    close_list()
    return "".join(out)
