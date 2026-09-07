"""搭子主窗口（Live2D 版，Alife 同架构）。

- QWebEngineView 透明窗口渲染 Live2D（assets/live2d/web + models/vvm，本地 HTTP 服务）
- HTML 页面承载：伙伴、气泡、输入框、点击/连击/视线/拖拽/右键
- Python 侧：轮询事件（发送/点击/菜单/收起）、JS 控制（表情/口型/气泡/悬停）、随机移动、右键菜单
- 伙伴常驻：大窗打开时悬停区关闭、伙伴保持可见（Q6/Q7）
"""

from __future__ import annotations

import json
import logging
import random
import threading
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QCursor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QInputDialog, QMenu, QVBoxLayout, QWidget

from JChat.config import PROJECT_ROOT

logger = logging.getLogger("JChat.companion")

try:
    import keyboard
except ImportError:  # pragma: no cover
    keyboard = None

WEB_ROOT = PROJECT_ROOT / "assets" / "live2d" / "web"
MODEL_ROOT = PROJECT_ROOT / "assets" / "live2d" / "models" / "vvm"

POKE_TEXT = ["嘿嘿～", "怎么啦？", "戳我干嘛～", "痒痒的！", "今天也要加油哦！"]
COMBO_TEXT = ["好痒好痒！别戳啦～", "再戳我就生气啦！", "哇！被你戳出爱心了！"]


class _Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        path = urllib.parse.unquote(path.split("?", 1)[0])
        if path.startswith("/model/"):
            return str(MODEL_ROOT / path[len("/model/"):])
        if path.startswith("/web/"):
            return str(WEB_ROOT / path[len("/web/"):])
        return str(WEB_ROOT / path.lstrip("/"))

    def log_message(self, *args):  # noqa: N802
        pass


class CompanionWindow(QWidget):
    send_requested = Signal(str)
    open_chat_requested = Signal()
    hover_collapsed = Signal()

    def __init__(self, config: dict, on_settings=None):
        super().__init__()
        self.config = config
        self.on_settings = on_settings
        self.chat_window_open = False
        self.pending_proactive: str | None = None
        self.direction = random.choice([-1, 1])
        self._server = None
        self._port = 0
        self._init_ui()
        self._init_server()
        self._init_poll()
        self._init_movement()
        self._init_hotkeys()

    # ------------------------------------------------------------ UI
    def _init_ui(self) -> None:
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(480, 560)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.width() - self.width() - 400, screen.height() - self.height() - 80)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView(self)
        self.view.setContextMenuPolicy(Qt.NoContextMenu)
        self.view.page().setBackgroundColor(QColor(0, 0, 0, 0))
        layout.addWidget(self.view)

        self.menu = QMenu(self)
        self.menu.addAction(QAction("💬 对话详情", self, triggered=self._menu_open_chat))
        self.menu.addAction(QAction("✏️ 改昵称", self, triggered=self._change_nickname))
        self.menu.addAction(
            QAction("⚙️ 设置", self, triggered=lambda: self.on_settings and self.on_settings())
        )
        self.menu.addSeparator()
        self.menu.addAction(QAction("退出", self, triggered=self._quit_app))

    def _init_server(self) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        model_url = "/model/" + urllib.parse.quote("vvm.model3.json")
        self.view.load(QUrl(f"http://127.0.0.1:{self._port}/web/index.html?model={model_url}"))
        QTimer.singleShot(6000, self._check_loaded)

    def _check_loaded(self) -> None:
        self.view.page().runJavaScript(
            "window.__modelLoaded ? 'loaded' : ('ERR:' + window.__loadError)",
            lambda r: logger.info("Live2D %s", r),
        )

    # ------------------------------------------------------------ JS bridge
    def _js(self, code: str) -> None:
        self.view.page().runJavaScript(code)

    def set_expression(self, name: str) -> None:
        self._js(f"setExpression({json.dumps(name)})")

    def set_talking(self, on: bool) -> None:
        self._js(f"setTalking({str(on).lower()})")

    def set_gaze(self, on: bool) -> None:
        self._js(f"setGaze({str(on).lower()})")

    def set_chat_window_open(self, open_: bool) -> None:
        self.chat_window_open = open_
        self._js(f"setOverlayVisible({str(not open_).lower()})")

    def show_reply(self, text: str, tools: list | None = None) -> None:
        self.pending_proactive = None
        payload = [
            {"name": t.name, "status": t.status, "output_preview": t.output_preview}
            for t in (tools or [])
        ]
        self._js(f"setBubble({json.dumps(text)}, {json.dumps(payload)})")

    def show_proactive(self, text: str) -> None:
        self.pending_proactive = text
        self._js(f"setBubble({json.dumps(text)}, [])")

    def _init_poll(self) -> None:
        self._poll = QTimer(self)
        self._poll.setInterval(200)
        self._poll.timeout.connect(self._poll_events)
        self._poll.start()

    def _poll_events(self) -> None:
        self.view.page().runJavaScript(
            "JSON.stringify((function(){ var s = (window.__takeSend && window.__takeSend()) || null;"
            " var e = (window.__takeEvents && window.__takeEvents()) || [];"
            " return {send: s, events: e}; })())",
            self._handle_events,
        )

    def _handle_events(self, result) -> None:
        if not isinstance(result, str) or not result:
            return
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            return
        if data.get("send"):
            self.send_requested.emit(data["send"])
        for ev in data.get("events") or []:
            self._handle_event(ev)

    def _handle_event(self, ev: dict) -> None:
        t = ev.get("type")
        if t == "poke":
            self.set_expression(random.choice(["happy", "shy", "surprised"]))
            self._js("bounce()")
            self._js(f"setBubble({json.dumps(random.choice(POKE_TEXT))}, [])")
        elif t == "combo":
            self.set_expression("happy")
            self._js("bounce()")
            self._js(f"setBubble({json.dumps(random.choice(COMBO_TEXT))}, [])")
        elif t == "drag":
            self.move(self.x() + int(ev.get("dx", 0)), self.y() + int(ev.get("dy", 0)))
        elif t == "menu":
            self.menu.popup(QCursor.pos())
        elif t == "open_chat":
            self._menu_open_chat()
        elif t == "collapsed":
            self.hover_collapsed.emit()

    def _menu_open_chat(self) -> None:
        self.open_chat_requested.emit()

    def _quit_app(self) -> None:
        QApplication.instance().quit()

    def _change_nickname(self) -> None:
        new_name, ok = QInputDialog.getText(
            self, "改昵称", "请输入新昵称：", text=self.config["companion"]["nickname"]
        )
        if ok and new_name:
            self.config["companion"]["nickname"] = new_name

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

    # ------------------------------------------------------------ hotkeys
    def _init_hotkeys(self) -> None:
        if keyboard is None:
            return
        shortcut = self.config["companion"]["shortcut_chat"]

        def listener() -> None:
            keyboard.add_hotkey(shortcut, lambda: QTimer.singleShot(0, self._menu_open_chat))
            keyboard.wait()

        threading.Thread(target=listener, daemon=True).start()
