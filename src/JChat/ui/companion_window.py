"""搭子主窗口（Pet-GPT 基线迁移）：无边框透明置顶、gif 动画、拖拽、随机移动、主动搭话气泡。"""

from __future__ import annotations

import random
import threading

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QMovie
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGraphicsDropShadowEffect,
    QInputDialog,
    QLabel,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from JChat.config import PROJECT_ROOT

try:
    import keyboard
except ImportError:  # pragma: no cover
    keyboard = None


class CompanionWindow(QWidget):
    def __init__(self, config: dict, on_open_chat=None, on_settings=None, on_proactive=None):
        super().__init__()
        self.config = config
        self.on_open_chat = on_open_chat
        self.on_settings = on_settings
        self.on_proactive = on_proactive
        self.chat_window_open = False
        self.drag_position = None
        self.direction = random.choice([-1, 1])
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
        self.setFixedSize(self.pet_width + 20, self.pet_height + 20)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.width() - self.width() - 500, screen.height() - self.height() - 100)

        icon_path = PROJECT_ROOT / c["icon"]
        self.pet_movie = QMovie(str(icon_path) if icon_path.exists() else str(icon_path))
        self.pet_movie.setScaledSize(QSize(self.pet_width, self.pet_height))
        self.pet_label = QLabel(self)
        self.pet_label.setMovie(self.pet_movie)
        self.pet_movie.start()

        layout = QVBoxLayout(self)
        layout.addWidget(self.pet_label)
        layout.setAlignment(Qt.AlignCenter)
        self.setLayout(layout)

        self.menu = QMenu(self)
        self.menu.addAction(QAction("💬 打开聊天", self, triggered=self._menu_open_chat))
        self.menu.addAction(QAction("🎨 更换形象", self, triggered=self._change_icon))
        self.menu.addAction(QAction("✏️ 改昵称", self, triggered=self._change_nickname))
        self.menu.addAction(
            QAction("⚙️ 设置", self, triggered=lambda: self.on_settings and self.on_settings())
        )
        self.menu.addSeparator()
        self.menu.addAction(QAction("退出", self, triggered=self.close))

        self.bubble = QLabel(self.parent() if self.parent() else None)
        self.bubble.setWindowFlags(Qt.SplashScreen)
        self.bubble.setStyleSheet(
            "background-color:#fff7e0; color:#3a2c00; border-radius:12px; padding:8px 12px; font-size:13px;"
        )
        self.bubble.setGraphicsEffect(QGraphicsDropShadowEffect(blurRadius=8, xOffset=0, yOffset=2))
        self.bubble.hide()
        self.show()

    # ------------------------------------------------------------ movement
    def _init_movement(self) -> None:
        c = self.config["companion"]
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_position)
        self.toggle_walk(c["random_walk"])
        screen = QApplication.primaryScreen().availableGeometry()
        self.max_x = screen.width() - self.width()
        self.max_y = screen.height() - self.height()
        self.stop_timer = QTimer()
        self.stop_timer.timeout.connect(self._restart_movement)
        self.movement_timer = QTimer()
        self.movement_timer.timeout.connect(self._stop_movement)

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

    def _restart_movement(self) -> None:
        self.stop_timer.stop()
        self.movement_timer.stop()
        self.direction = random.choice([-1, 1])

    def _stop_movement(self) -> None:
        self.stop_timer.stop()
        self.movement_timer.stop()
        self.direction = 0

    # ------------------------------------------------------------ events
    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802
        if event.buttons() == Qt.LeftButton and self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)

    def contextMenuEvent(self, event):  # noqa: N802
        self.menu.exec(event.globalPos())

    def _menu_open_chat(self) -> None:
        if self.on_open_chat:
            self.on_open_chat()

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

    # ------------------------------------------------------------ bubble & proactive
    def show_bubble(self, text: str, ms: int = 4000) -> None:
        if not text:
            return
        self.bubble.setText(text)
        self.bubble.adjustSize()
        global_pos = self.mapToGlobal(QPoint(self.pet_label.width(), 0))
        self.bubble.move(global_pos.x(), global_pos.y() - self.bubble.height())
        self.bubble.show()
        QTimer.singleShot(ms, self.bubble.hide)

    def trigger_proactive(self) -> None:
        if self.on_proactive:
            self.on_proactive()

    def is_chat_window_open(self) -> bool:
        return self.chat_window_open

    # ------------------------------------------------------------ hotkeys
    def _init_hotkeys(self) -> None:
        if keyboard is None:
            return
        shortcut = self.config["companion"]["shortcut_chat"]

        def listener() -> None:
            keyboard.add_hotkey(shortcut, lambda: QTimer.singleShot(0, self._menu_open_chat))
            keyboard.wait()

        threading.Thread(target=listener, daemon=True).start()
