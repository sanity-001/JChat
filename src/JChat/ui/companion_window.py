"""搭子主窗口：无边框透明置顶 gif + 悬停交互（绝对定位，伙伴本体固定不位移）。

交互（Q1/Q2/Q16/Q17）：
- 悬停伙伴/气泡/输入框区域 → 唤出悬停区；光标真正离开窗口 1.5s 后收起（打字不受影响）
- 气泡在伙伴上方（最新一条回复，可滚动，工具胶囊，可跳大窗）；输入框在伙伴下方
- 主动搭话：气泡 + 输入框同时唤出（只随离开收起）
- 伙伴常驻：大窗打开时悬停区关闭、伙伴保持可见（Q6/Q7）
"""

from __future__ import annotations

import random
import threading

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor, QMovie
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
        self._bubble_active = False
        self._bubble_zone = BUBBLE_ZONE
        self._away_since: float | None = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(200)
        self._poll_timer.timeout.connect(self._poll_hover)
        self._poll_timer.start()
        self._reply_timer = QTimer(self)
        self._reply_timer.setSingleShot(True)
        self._reply_timer.timeout.connect(self._expire_bubble)
        self._init_ui()
        self._init_movement()
        self._init_hotkeys()

    # ------------------------------------------------------------ UI
    def _init_ui(self) -> None:
        c = self.config["companion"]
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.pet_width = c["width"]
        self.pet_height = c["height"]

        # 气泡区（上方，绝对定位）
        self.bubble_host = QWidget(self)
        self.bubble_layout = QVBoxLayout(self.bubble_host)
        self.bubble_layout.setContentsMargins(6, 4, 6, 4)
        self.bubble_layout.addStretch()
        self.bubble_host.hide()

        # 伙伴本体（中间，绝对定位，悬停/收起均不移动）
        icon_path = PROJECT_ROOT / c["icon"]
        self.pet_movie = QMovie(str(icon_path))
        self.pet_movie.setScaledSize(QSize(self.pet_width, self.pet_height))
        self.pet_label = QLabel(self)
        self.pet_label.setMovie(self.pet_movie)
        self.pet_movie.start()

        # 输入区（下方，绝对定位）
        self.input_host = QWidget(self)
        input_layout = QVBoxLayout(self.input_host)
        input_layout.setContentsMargins(10, 6, 10, 6)
        self.input = QLineEdit()
        self.input.setObjectName("HoverInput")
        self.input.setPlaceholderText("说点什么…（Enter 发送）")
        self.input.returnPressed.connect(self._send)
        input_layout.addWidget(self.input)
        self.input_host.hide()

        self._relayout()
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.width() - self.width() - 400, screen.height() - self.height() - 80)
        self._init_menu()

    def _relayout(self) -> None:
        w = self.pet_width + 60
        h = self._bubble_zone + self.pet_height + INPUT_ZONE + 30
        self.setFixedSize(w, h)
        pet_x = (w - self.pet_width) // 2
        pet_y = self._bubble_zone + 6
        self.pet_label.setGeometry(pet_x, pet_y, self.pet_width, self.pet_height)
        self.bubble_host.setGeometry(5, 2, w - 10, self._bubble_zone - 8)
        self.input_host.setGeometry(5, h - INPUT_ZONE - 4, w - 10, INPUT_ZONE)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._relayout()
        super().resizeEvent(event)

    def _init_menu(self) -> None:
        self.menu = QMenu(self)
        self.menu.addAction(QAction("💬 对话详情", self, triggered=self._menu_open_chat))
        self.menu.addAction(QAction("🎨 更换形象", self, triggered=self._change_icon))
        self.menu.addAction(QAction("✏️ 改昵称", self, triggered=self._change_nickname))
        self.menu.addAction(
            QAction("⚙️ 设置", self, triggered=lambda: self.on_settings and self.on_settings())
        )
        self.menu.addSeparator()
        self.menu.addAction(QAction("退出", self, triggered=self._quit_app))

    def _quit_app(self) -> None:
        QApplication.instance().quit()

    def _menu_open_chat(self) -> None:
        self.open_chat_requested.emit()

    # ------------------------------------------------------------ hover
    def _poll_hover(self) -> None:
        """轮询光标：在窗口内保持/唤出；离开累计 1.5s 收起（打字/子控件不受影响）。"""
        import time

        if self.chat_window_open:
            return
        inside = not self._cursor_outside()
        if inside:
            self._away_since = None
            if not self._hover_visible:
                self._show_hover()
        elif self._hover_visible:
            if self._away_since is None:
                self._away_since = time.time()
            elif time.time() - self._away_since >= COLLAPSE_MS / 1000:
                self._collapse()

    def _cursor_outside(self) -> bool:
        rect = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
        return not rect.contains(QCursor.pos())

    def _show_hover(self) -> None:
        if self.chat_window_open:
            return
        self._hover_visible = True
        self._away_since = None
        if self._bubble_active:
            self.bubble_host.show()
        self.input_host.show()

    def _collapse(self) -> None:
        self._hover_visible = False
        self._away_since = None
        self.bubble_host.hide()
        self.input_host.hide()
        self.input.clearFocus()
        self.hover_collapsed.emit()

    def set_chat_window_open(self, open_: bool) -> None:
        self.chat_window_open = open_
        if open_:
            self._collapse()

    # ------------------------------------------------------------ bubble
    def _set_bubble(self, text: str, tools: list | None = None) -> None:
        while self.bubble_layout.count() > 1:
            item = self.bubble_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        bubble = MessageBubble(
            "companion",
            text,
            max_height=None,
            show_full_link=True,
            on_full_link=self._menu_open_chat,
            font_size=self.config["ui"]["font_size"],
        )
        for ev in tools or []:
            bubble.add_tool_capsule(ev.name, ev.status, ev.output_preview)
        bubble.installEventFilter(self)
        bubble.text_browser.installEventFilter(self)
        self.bubble_layout.insertWidget(0, bubble, alignment=Qt.AlignHCenter)

        # 气泡随内容增高：窗口向上扩展（底部/伙伴位置不变）
        hint_h = bubble.sizeHint().height()
        self._bubble_zone = max(BUBBLE_ZONE, hint_h + 24)
        old_h = self.height()
        self._relayout()
        delta = self.height() - old_h
        if delta > 0:
            self.move(self.x(), self.y() - delta)

    def _expire_bubble(self) -> None:
        """单次回复存在时间到：气泡消失（输入框不受影响）。"""
        self._bubble_active = False
        if self._hover_visible:
            self.bubble_host.hide()

    def show_reply(self, text: str, tools: list | None = None) -> None:
        self.pending_proactive = None
        self._set_bubble(text, tools)
        self._bubble_active = True
        self._reply_timer.start(self.config["companion"].get("reply_ttl_seconds", 30) * 1000)
        self._show_hover()

    def show_proactive(self, text: str) -> None:
        self.pending_proactive = text
        self._set_bubble(text)
        self._bubble_active = True
        self._reply_timer.start(self.config["companion"].get("reply_ttl_seconds", 30) * 1000)
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
