"""搭子主窗口（重构）：无边框透明置顶 gif + 悬停交互。

交互（Q1/Q2/Q16/Q17）：
- 悬停伙伴本体（含气泡/输入框区域）→ 唤出悬停区；离开 1.5s 收起
- 气泡在伙伴上方（只显示最新一条回复，可滚动，工具胶囊，可跳大窗）
- 输入框在伙伴下方（Enter 发送）
- 主动搭话：气泡 + 输入框同时唤出（不因输入收起）
- 伙伴常驻：大窗打开时悬停区关闭、伙伴保持可见（Q6/Q7）
"""

from __future__ import annotations

import random
import threading

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QMovie
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from JChat.config import PROJECT_ROOT
from JChat.ui.widgets import MessageBubble

try:
    import keyboard
except ImportError:  # pragma: no cover
    keyboard = None

BUBBLE_ZONE = 320
INPUT_ZONE = 90
COLLAPSE_MS = 1500


class CompanionWindow(QWidget):
    send_requested = Signal(str)
    open_chat_requested = Signal()
    hover_collapsed = Signal()

    def __init__(self, config: dict, on_settings=None):
        super().__init__()
        self.config = config
        self.on_settings = on_settings
        self.chat_window_open = False
        self.drag_position = None
        self.direction = random.choice([-1, 1])
        self.pending_proactive: str | None = None
        self._hover_visible = False
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self._collapse)
        self._init_ui()
        self._init_movement()
        self._init_hotkeys()

    # ------------------------------------------------------------ UI
    def _init_ui(self) -> None:
        c = self.config["companion"]
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.pet_width = c["width"]
        self.pet_height = c["height"]
        self.setFixedSize(self.pet_width + 60, BUBBLE_ZONE + self.pet_height + INPUT_ZONE + 30)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.width() - self.width() - 400, screen.height() - self.height() - 80)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(4)

        # 气泡区（上方）
        self.bubble_host = QWidget(self)
        self.bubble_host.setFixedHeight(BUBBLE_ZONE - 10)
        self.bubble_layout = QVBoxLayout(self.bubble_host)
        self.bubble_layout.setContentsMargins(6, 4, 6, 4)
        self.bubble_layout.addStretch()
        self.bubble_host.hide()
        layout.addWidget(self.bubble_host)

        # 伙伴本体（中间）
        icon_path = PROJECT_ROOT / c["icon"]
        self.pet_movie = QMovie(str(icon_path))
        self.pet_movie.setScaledSize(QSize(self.pet_width, self.pet_height))
        self.pet_label = QLabel(self)
        self.pet_label.setMovie(self.pet_movie)
        self.pet_movie.start()
        layout.addWidget(self.pet_label, alignment=Qt.AlignHCenter | Qt.AlignVCenter)

        # 输入区（下方）
        self.input_host = QWidget(self)
        self.input_host.setFixedHeight(INPUT_ZONE)
        input_layout = QVBoxLayout(self.input_host)
        input_layout.setContentsMargins(10, 6, 10, 6)
        self.input = QLineEdit()
        self.input.setObjectName("HoverInput")
        self.input.setPlaceholderText("说点什么…（Enter 发送）")
        self.input.returnPressed.connect(self._send)
        input_layout.addWidget(self.input)
        self.input_host.hide()
        layout.addWidget(self.input_host)

        self._init_menu()

    def _init_menu(self) -> None:
        self.menu = QMenu(self)
        self.menu.addAction(QAction("💬 对话详情", self, triggered=self._menu_open_chat))
        self.menu.addAction(QAction("🎨 更换形象", self, triggered=self._change_icon))
        self.menu.addAction(QAction("✏️ 改昵称", self, triggered=self._change_nickname))
        self.menu.addAction(
            QAction("⚙️ 设置", self, triggered=lambda: self.on_settings and self.on_settings())
        )
        self.menu.addSeparator()
        self.menu.addAction(QAction("退出", self, triggered=self.close))

    def _menu_open_chat(self) -> None:
        self.open_chat_requested.emit()

    # ------------------------------------------------------------ hover
    def _show_hover(self) -> None:
        if self.chat_window_open:
            return
        self._hover_visible = True
        self._collapse_timer.stop()
        self.input_host.show()
        if self.bubble_host.isHidden() and not self.pending_proactive:
            self.bubble_host.show()
        else:
            self.bubble_host.show()

    def _collapse(self) -> None:
        self._hover_visible = False
        self.bubble_host.hide()
        self.input_host.hide()
        self.input.clearFocus()
        self.hover_collapsed.emit()

    def set_chat_window_open(self, open_: bool) -> None:
        self.chat_window_open = open_
        if open_:
            self._collapse()
        else:
            self._collapse_timer.stop()

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        self._collapse_timer.stop()
        if not self.chat_window_open:
            self._show_hover()

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self._collapse_timer.start(COLLAPSE_MS)

    # ------------------------------------------------------------ bubble
    def _set_bubble(self, text: str, tools: list | None = None) -> None:
        while self.bubble_layout.count() > 1:
            item = self.bubble_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        bubble = MessageBubble(
            "companion",
            text,
            max_height=220,
            show_full_link=True,
            on_full_link=self._menu_open_chat,
            font_size=self.config["ui"]["font_size"],
        )
        for ev in tools or []:
            bubble.add_tool_capsule(ev.name, ev.status, ev.output_preview)
        self.bubble_layout.insertWidget(0, bubble, alignment=Qt.AlignHCenter)

    def show_reply(self, text: str, tools: list | None = None) -> None:
        """显示最新回复气泡（悬停交互：随输入框同进退）。"""
        self.pending_proactive = None
        self._set_bubble(text, tools)
        self._show_hover()

    def show_proactive(self, text: str) -> None:
        """主动搭话：气泡 + 输入框同时唤出（不因输入收起，只随离开收起）。"""
        self.pending_proactive = text
        self._set_bubble(text)
        self._show_hover()

    def _send(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.send_requested.emit(text)

    # ------------------------------------------------------------ movement
    def _init_movement(self) -> None:
        c = self.config["companion"]
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_position)
        self.toggle_walk(c["random_walk"])
        screen = QApplication.primaryScreen().availableGeometry()
        self.max_x = screen.width() - self.width()
        self.max_y = screen.height() - self.height()

    def toggle_walk(self, state: bool) -> None:
        if state:
            self.timer.start(50)
        else:
            self.timer.stop()

    def _update_position(self) -> None:
        if self.direction == 0:
            return
        pos = self.pos()
        new_x = pos.x() + self.direction
        if new_x >= self.max_x:
            self.direction = -1
        elif new_x <= 0:
            self.direction = 1
        self.move(QPoint(new_x, pos.y()))

    # ------------------------------------------------------------ events
    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self.pet_label.geometry().contains(
            event.position().toPoint()
        ):
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802
        if event.buttons() == Qt.LeftButton and self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)

    def contextMenuEvent(self, event):  # noqa: N802
        self.menu.exec(event.globalPos())

    def _change_icon(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择新形象", "", "Images (*.png *.jpg *.gif)")
        if path:
            self.pet_movie.stop()
            self.pet_movie.setFileName(path)
            self.pet_movie.setScaledSize(QSize(self.pet_width, self.pet_height))
            self.pet_movie.start()
            self.config["companion"]["icon"] = path

    def _change_nickname(self) -> None:
        new_name, ok = QInputDialog.getText(
            self, "改昵称", "请输入新昵称：", text=self.config["companion"]["nickname"]
        )
        if ok and new_name:
            self.config["companion"]["nickname"] = new_name

    # ------------------------------------------------------------ hotkeys
    def _init_hotkeys(self) -> None:
        if keyboard is None:
            return
        shortcut = self.config["companion"]["shortcut_chat"]

        def listener() -> None:
            keyboard.add_hotkey(shortcut, lambda: QTimer.singleShot(0, self._menu_open_chat))
            keyboard.wait()

        threading.Thread(target=listener, daemon=True).start()
