"""聊天窗（票据 006 C 方案）：伙伴卡片 + 渐变贴纸气泡 + 便签工具卡 + 记忆 chips。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from JChat.ui.widgets import Bubble, MemoryChip, ToolCard


class ChatWindow(QDialog):
    send_requested = Signal(str)
    closed = Signal()

    def __init__(self, config: dict, memory_count_fn=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.memory_count_fn = memory_count_fn
        self.setWindowTitle(f"与{config['companion']['nickname']}聊天")
        self.setObjectName("Root")
        self.resize(920, 640)
        self._build_ui()

    # ---------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 伙伴卡片
        side = QFrame()
        side.setObjectName("Card")
        side.setFixedWidth(270)
        side.setStyleSheet("QFrame#Card { background:#12151d; border:none; border-radius:0; }")
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(24, 40, 24, 24)
        side_layout.setAlignment(Qt.AlignTop)

        avatar = QLabel("小")
        avatar.setFixedSize(120, 120)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #ff8a5c, "
            "stop:0.5 #ff4f8b, stop:1 #7c5cff);"
            "color:white; font-size:48px; font-weight:700; border-radius:60px;"
        )
        side_layout.addWidget(avatar, alignment=Qt.AlignHCenter)

        name = QLabel(self.config["companion"]["nickname"])
        name.setObjectName("Title")
        name.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(name)

        persona = QLabel(self.config["companion"]["persona"][:60])
        persona.setObjectName("Muted")
        persona.setWordWrap(True)
        persona.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(persona)

        self.welcome = QLabel("💬 想聊点什么？我记性很好哦～")
        self.welcome.setStyleSheet(
            "background:#1b2230; color:#e7ecf5; border-radius:14px; padding:10px 14px; font-size:13px;"
        )
        self.welcome.setWordWrap(True)
        side_layout.addSpacing(18)
        side_layout.addWidget(self.welcome)
        side_layout.addStretch()
        root.addWidget(side)

        # 聊天卡片
        chat = QFrame()
        chat.setObjectName("Card")
        chat_layout = QVBoxLayout(chat)
        chat_layout.setContentsMargins(20, 16, 20, 16)

        header = QHBoxLayout()
        title = QLabel(f"{self.config['companion']['nickname']} · 对话")
        title.setObjectName("Title")
        header.addWidget(title)
        header.addStretch()
        self.mem_chip = MemoryChip("🧠 记忆已载入")
        header.addWidget(self.mem_chip)
        chat_layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.msg_host = QWidget()
        self.msg_layout = QVBoxLayout(self.msg_host)
        self.msg_layout.setContentsMargins(4, 10, 4, 10)
        self.msg_layout.setSpacing(10)
        self.msg_layout.addStretch()
        self.scroll.setWidget(self.msg_host)
        chat_layout.addWidget(self.scroll, stretch=1)

        input_row = QHBoxLayout()
        self.input = QPlainTextEdit()
        self.input.setObjectName("Input")
        self.input.setPlaceholderText("说点什么…（Enter 发送）")
        self.input.setFixedHeight(52)
        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("Send")
        self.send_btn.clicked.connect(self._send)
        input_row.addWidget(self.input, stretch=1)
        input_row.addWidget(self.send_btn)
        chat_layout.addLayout(input_row)
        root.addWidget(chat, stretch=1)

        self._refresh_mem_chip()

    def _refresh_mem_chip(self) -> None:
        if self.memory_count_fn:
            count = self.memory_count_fn()
            self.mem_chip.setText(f"🧠 {count} 条记忆")

    # ---------------------------------------------------------------- messages
    def add_user_message(self, text: str) -> None:
        self._append_bubble("user", text)
        self._scroll_bottom()

    def add_companion_message(self, text: str) -> None:
        self._append_bubble("companion", text)
        self._scroll_bottom()

    def add_tool_card(self, name: str, status: str, output: str = "") -> ToolCard:
        card = ToolCard(name, status, output)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(card, stretch=0)
        self.msg_layout.insertLayout(self.msg_layout.count() - 1, row)
        self._scroll_bottom()
        return card

    def update_tool_card(self, card: ToolCard, status: str, output: str = "") -> None:
        card.update_status(status, output)
        self._scroll_bottom()

    def set_busy(self, busy: bool) -> None:
        self.input.setEnabled(not busy)
        self.send_btn.setEnabled(not busy)

    def _append_bubble(self, role: str, text: str) -> None:
        bubble = Bubble(role, text, font_size=self.config["ui"]["font_size"])
        row = QHBoxLayout()
        if role == "user":
            row.addStretch()
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch()
        self.msg_layout.insertLayout(self.msg_layout.count() - 1, row)

    def _scroll_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ---------------------------------------------------------------- events
    def _send(self) -> None:
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self.send_requested.emit(text)

    def closeEvent(self, event):  # noqa: N802
        self.closed.emit()
        event.accept()
