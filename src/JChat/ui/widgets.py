"""自绘 UI 组件：渐变气泡（Bubble）、便签风工具卡（ToolCard）。"""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

MAX_BUBBLE_WIDTH = 460


class Bubble(QWidget):
    """贴纸气泡：圆角 + 尾部小尖角 + 渐变（用户）/ 深色（搭子）。"""

    def __init__(self, role: str, text: str, font_size: int = 14, parent=None):
        super().__init__(parent)
        self.role = role
        self.text = text
        self._font = QFont("Microsoft YaHei", font_size)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def _document(self) -> object:
        from PySide6.QtGui import QTextDocument

        doc = QTextDocument()
        doc.setDefaultFont(self._font)
        doc.setDocumentMargin(10)
        doc.setTextWidth(MAX_BUBBLE_WIDTH)
        doc.setPlainText(self.text)
        return doc

    def sizeHint(self):  # noqa: N802
        doc = self._document()
        return doc.size().toSize() + QSize(28, 24)

    def paintEvent(self, event):  # noqa: N802
        doc = self._document()
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        radius = 18
        tail = 12
        if self.role == "user":
            path.addRoundedRect(rect, radius, radius)
            path.moveTo(rect.right() - radius, rect.top() + radius)
            path.lineTo(rect.right() + tail, rect.top() + radius)
            path.lineTo(rect.right() - radius + 4, rect.top() + radius + 14)
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0, QColor("#4f8cff"))
            grad.setColorAt(1, QColor("#7c5cff"))
        else:
            path.addRoundedRect(rect, radius, radius)
            path.moveTo(rect.left() + radius, rect.top() + radius)
            path.lineTo(rect.left() - tail, rect.top() + radius)
            path.lineTo(rect.left() + radius - 4, rect.top() + radius + 14)
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0, QColor("#202843"))
            grad.setColorAt(1, QColor("#1b2230"))
        painter.fillPath(path, grad)
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.drawPath(path)

        doc.drawContents(painter, self.rect().adjusted(10, 6, -10, -6))


class ToolCard(QFrame):
    """便签风工具调用卡片：标题可点击折叠，显示状态与输出。"""

    def __init__(self, name: str, status: str = "running", output: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("ToolCard")
        self.setStyleSheet(
            "QFrame#ToolCard { background:#fff7e0; border:none; border-radius:12px; }"
            "QLabel { color:#3a2c00; } QPlainTextEdit { background:transparent; color:#5a4600; border:none; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        self.head = QHBoxLayout()
        self.icon = QLabel("🔧")
        self.title = QLabel(name)
        self.title.setStyleSheet("font-weight:700; color:#3a2c00;")
        self.status_label = QLabel(status)
        self.status_label.setStyleSheet("font-size:11px; color:#a08a3a;")
        self.arrow = QLabel("▾")
        self.head.addWidget(self.icon)
        self.head.addWidget(self.title)
        self.head.addWidget(self.status_label)
        self.head.addStretch()
        self.head.addWidget(self.arrow)
        layout.addLayout(self.head)
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
    def __init__(self, text: str, color: str = "#4f8cff", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            f"background-color: rgba({_rgb(color)},0.15); color:{color};"
            "border-radius:10px; padding:3px 10px; font-size:11px;"
        )


def _rgb(color: str) -> str:
    c = QColor(color)
    return f"{c.red()},{c.green()},{c.blue()}"
