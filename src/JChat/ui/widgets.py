"""马卡龙风格自绘组件：回复气泡（MessageBubble）、工具胶囊、便签工具卡、记忆 chips、待机头像。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

PALETTE = {
    "user": {"bg": "#FFE0EC", "fg": "#8A4A5E"},
    "companion": {"bg": "#DFF5E1", "fg": "#3A5A40"},
    "capsule": {"bg": "#FFF6C9", "fg": "#8A6D00"},
    "chip": "#5B9BD5",
}


class IdleAvatar(QWidget):
    """大窗侧栏头像：播放精灵图指定行的帧动画（默认待机行），圆形裁剪。"""

    FRAME_W, FRAME_H = 192, 208

    def __init__(
        self,
        size: int = 110,
        row: int = 0,
        frames: int = 6,
        fps: int = 8,
        sheet_path=None,
        parent=None,
    ):
        super().__init__(parent)
        self._size = size
        self._row = row
        self._frames = max(1, frames)
        self._idx = 0
        self._sheet: QImage | None = None
        if sheet_path:
            img = QImage(str(sheet_path))
            if not img.isNull():
                self._sheet = img
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(int(1000 / fps))

    def _step(self) -> None:
        self._idx = (self._idx + 1) % self._frames
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self._size, self._size, self._size / 2, self._size / 2)
        p.setClipPath(path)
        # 渐变底（马卡龙粉紫）+ 精灵帧
        from PySide6.QtGui import QLinearGradient

        grad = QLinearGradient(0, 0, self._size, self._size)
        grad.setColorAt(0, QColor("#FFB6C9"))
        grad.setColorAt(1, QColor("#C9A9FF"))
        p.fillRect(self.rect(), grad)
        if self._sheet is not None:
            sx = (self._idx % self._frames) * self.FRAME_W
            src = self._sheet.copy(sx, self._row * self.FRAME_H, self.FRAME_W, self.FRAME_H)
            scaled = src.scaled(self._size, self._size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(
                (self._size - scaled.width()) // 2,
                self._size - scaled.height(),
                QPixmap.fromImage(scaled),
            )
        p.end()


class MessageBubble(QFrame):
    """自适应回复气泡：高度随完整内容（文档实际高度），可选上限（大窗可无上限）。"""

    TEXT_WIDTH = 320

    def __init__(
        self,
        role: str,
        text: str,
        parent=None,
        max_height: int | None = None,
        show_full_link: bool = False,
        on_full_link=None,
        font_size: int = 14,
        assistant_font: str = "楷体",
    ):
        super().__init__(parent)
        role = role if role in PALETTE else "companion"
        color = PALETTE[role]
        self.setStyleSheet(
            f"QFrame {{ background-color: {color['bg']}; border: none; border-radius: 20px; }}"
        )
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        self.text_browser = QTextBrowser()
        self.text_browser.setFrameShape(QFrame.NoFrame)
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setStyleSheet(
            f"QTextBrowser {{ background: transparent; color: {color['fg']};"
            f" font-size: {font_size}px; border: none; }}"
        )
        if role == "companion":
            from JChat.ui.markdown import md_to_html

            self.text_browser.setHtml(md_to_html(text, body_font=assistant_font))
        else:
            self.text_browser.setPlainText(text)
        self.text_browser.setFixedWidth(self.TEXT_WIDTH)
        self.text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._autosize(max_height)
        layout.addWidget(self.text_browser)

        self.tool_row = QHBoxLayout()
        self.tool_row.setSpacing(6)
        layout.addLayout(self.tool_row)

        if show_full_link:
            self.full_link = QPushButton("查看全文 ↗")
            self.full_link.setCursor(Qt.PointingHandCursor)
            self.full_link.setStyleSheet(
                "QPushButton { background: transparent; border: none; color:#C9A9FF;"
                " font-size:12px; text-align:left; }"
            )
            self.full_link.clicked.connect(lambda: on_full_link and on_full_link())
            layout.addWidget(self.full_link, alignment=Qt.AlignLeft)

    def _autosize(self, max_height: int | None) -> None:
        """按文档实际高度设置气泡高度（完整内容自适应）。"""
        doc = self.text_browser.document()
        doc.setTextWidth(self.TEXT_WIDTH)
        height = int(doc.size().height()) + 22
        if max_height is not None:
            height = min(height, max_height)
        self.text_browser.setFixedHeight(height)

    def add_tool_capsule(self, name: str, status: str = "done", output: str = "") -> None:
        capsule = QPushButton(f"🔧 {name} {'✓' if status == 'done' else '✗'}")
        capsule.setCursor(Qt.PointingHandCursor)
        capsule.setStyleSheet(
            f"QPushButton {{ background:{PALETTE['capsule']['bg']}; color:{PALETTE['capsule']['fg']};"
            " border:none; border-radius:12px; padding:3px 10px; font-size:12px; }"
        )
        capsule.clicked.connect(lambda: self._toggle_output(capsule, output))
        self.tool_row.addWidget(capsule)

    def _toggle_output(self, capsule: QPushButton, output: str) -> None:
        for i in range(self.layout().count()):
            w = self.layout().itemAt(i).widget()
            if isinstance(w, QPlainTextEdit):
                w.setVisible(not w.isVisible())
                return
        out = QPlainTextEdit()
        out.setReadOnly(True)
        out.setMaximumHeight(120)
        out.setStyleSheet(
            f"QPlainTextEdit {{ background:{PALETTE['capsule']['bg']};"
            f" color:{PALETTE['capsule']['fg']}; border:none; border-radius:10px; font-size:12px; }}"
        )
        out.setPlainText(output)
        self.layout().addWidget(out)


class ToolCard(QFrame):
    """便签风工具调用卡片（大窗使用）：标题可点击折叠。"""

    def __init__(self, name: str, status: str = "running", output: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("ToolCard")
        self.setStyleSheet(
            "QFrame#ToolCard { background:#FFF6C9; border:none; border-radius:14px; }"
            "QLabel { color:#8A6D00; } QPlainTextEdit { background:transparent; color:#8A6D00; border:none; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        head = QHBoxLayout()
        self.title = QLabel(f"🔧 {name}")
        self.title.setStyleSheet("font-weight:700; color:#8A6D00;")
        self.status_label = QLabel(status)
        self.status_label.setStyleSheet("font-size:11px; color:#B59A3C;")
        self.arrow = QLabel("▾")
        head.addWidget(self.title)
        head.addWidget(self.status_label)
        head.addStretch()
        head.addWidget(self.arrow)
        layout.addLayout(head)
        self.body = QPlainTextEdit()
        self.body.setReadOnly(True)
        self.body.setMaximumHeight(140)
        self.body.setPlainText(output)
        self.body.hide()
        layout.addWidget(self.body)
        self._collapsed = True

    def mousePressEvent(self, event):  # noqa: N802
        self._collapsed = not self._collapsed
        self.body.setVisible(not self._collapsed)
        self.arrow.setText("▸" if self._collapsed else "▾")
        super().mousePressEvent(event)

    def update_status(self, status: str, output: str = "") -> None:
        self.status_label.setText(status)
        if output:
            self.body.setPlainText(output)


class MemoryChip(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        color = PALETTE["chip"]
        self.setStyleSheet(
            f"background-color:#E3F0FF; color:{color}; border-radius:11px; padding:3px 12px; font-size:11px;"
        )
