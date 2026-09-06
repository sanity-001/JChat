"""Live2D PoC：透明 QWebEngineView + 本地 HTTP 服务 + pixi-live2d-display。
验证：模型能否加载、透明、参数表导出。运行 25 秒自动退出。"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PySide6.QtCore import QUrl, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

PROJECT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT / "assets" / "live2d" / "web"
MODEL_ROOT = PROJECT / "assets" / "live2d" / "models" / "vvm"


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        path = urllib.parse.unquote(path.split("?", 1)[0])
        if path.startswith("/model/"):
            return str(MODEL_ROOT / path[len("/model/"):])
        if path.startswith("/web/"):
            return str(WEB_ROOT / path[len("/web/"):])
        return str(WEB_ROOT / path.lstrip("/"))

    def log_message(self, *args):  # noqa: N802
        pass


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    app = QApplication(sys.argv)
    view = QWebEngineView()
    view.setWindowTitle("JChat Pet PoC")
    view.resize(480, 640)
    view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    view.page().setBackgroundColor(QColor(0, 0, 0, 0))
    view.move(400, 200)
    model_url = "/model/" + urllib.parse.quote("vvm.model3.json")
    view.load(QUrl(f"http://127.0.0.1:{port}/web/index.html?model={model_url}"))
    view.show()

    state = {"params": None, "error": ""}

    def poll() -> None:
        view.page().runJavaScript(
            "JSON.stringify({loaded: window.__modelLoaded, err: window.__loadError,"
            " params: window.__params, hitAreas: window.__hitAreas, log: window.__log})",
            lambda result: _collect(result, state),
        )

    def finish() -> None:
        try:
            if state["params"] is not None:
                data = json.loads(state["params"])
                print("LOG:")
                for line in data["log"]:
                    print(" ", line)
                print(f"LOADED={data['loaded']} ERR={data['err']}")
                print("HITAREAS:", json.dumps(data.get("hitAreas", []), ensure_ascii=False))
                params = data.get("params") or []
                print(f"PARAMS({len(params)}):")
                for p in params:
                    print(f"  {p['id']}  default={p['def']:.2f}  range=[{p['min']:.2f},{p['max']:.2f}]")
            elif state["error"]:
                print("LOAD ERROR:", state["error"])
            else:
                print("NOT LOADED YET")
            sys.stdout.flush()
        finally:
            server.shutdown()
            app.quit()

    poll_timer = QTimer()
    poll_timer.timeout.connect(poll)
    poll_timer.start(1500)
    QTimer.singleShot(25000, finish)
    sys.exit(app.exec())


def _collect(result, state) -> None:
    if result is None:
        return
    if isinstance(result, str):
        try:
            data = json.loads(result)
            state["params"] = result
        except json.JSONDecodeError:
            state["error"] = result
    else:
        state["error"] = repr(result)


if __name__ == "__main__":
    main()
