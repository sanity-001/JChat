"""眼泪/黑角素材探测：Teers 主开关 + 泪阶 + 角/眼型开关。"""

from __future__ import annotations

import base64
import json
import os
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
OUT = Path(r"C:\Users\RUANZH~1\AppData\Local\Temp\opencode\param_probes")
OUT.mkdir(parents=True, exist_ok=True)
LOG = open(r"C:\Users\RUANZH~1\AppData\Local\Temp\opencode\tears_probe.log", "w", encoding="utf-8")


def log(msg) -> None:
    LOG.write(msg + "\n")
    LOG.flush()


PROBES = [
    ("base", {}),
    ("teers1", {"ParamTeers": 1, "ParamTeersT": 1, "Param170": 1, "Param126": 1, "Param132": 1}),
    ("teers2", {"ParamTeers": 1, "ParamTeersT": 1, "Param170": 1, "Param127": 1, "Param133": 1,
                "Param128": 1, "Param134": 1}),
    ("teers3", {"ParamTeers": 1, "ParamTeersT": 1, "Param170": 1, "Param162": 1, "Param126": 1,
                "Param132": 1, "Param130": 1, "Param137": 1}),
    ("teers4", {"ParamTeers": -1, "ParamTeersT": -1, "Param170": -1, "Param126": -1, "Param132": -1}),
    ("things", {"ParamThingsToggle": 1}),
    ("hat", {"ParamHat": 1}),
    ("eyechg", {"ParamEyeChange22": 1, "ParamEyeChange23": 1}),
    ("eyechg2", {"ParamEyeChange9": 1, "ParamEyeChange12": 1}),
    ("blackface", {"ParamBlackFace": 1}),
    ("tearsSad", {"ParamTeers": 1, "ParamTeersT": 1, "Param170": 1, "Param126": 1, "Param132": 1,
                  "ParamEyeLOpen": 0.5, "ParamEyeROpen": 0.5, "ParamMouthOpenY": 0.2}),
]


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
    log("start")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    app = QApplication(sys.argv)
    view = QWebEngineView()
    view.resize(480, 560)
    view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    view.page().setBackgroundColor(QColor(0, 0, 0, 0))
    model_url = "/model/" + urllib.parse.quote("vvm.model3.json")
    view.load(QUrl(f"http://127.0.0.1:{port}/web/index.html?model={model_url}"))
    view.show()

    state = {"idx": 0}

    def poll_loaded(attempt: int = 0) -> None:
        view.page().runJavaScript(
            "window.__modelLoaded ? 'ok' : 'ERR:' + window.__loadError",
            lambda r: _on_load(r, attempt),
        )

    def _on_load(r, attempt) -> None:
        if r == "ok":
            log("loaded")
            QTimer.singleShot(800, step)
        elif attempt < 40:
            QTimer.singleShot(500, lambda: poll_loaded(attempt + 1))
        else:
            log("load-fail " + str(r))
            finish()

    def step() -> None:
        idx = state["idx"]
        if idx >= len(PROBES):
            log("DONE")
            finish()
            return
        name, pairs = PROBES[idx]
        log("set " + name)
        view.page().runJavaScript("window.__probeSet(%s)" % json.dumps(pairs))
        QTimer.singleShot(1000, lambda: snap(name))

    def snap(name: str) -> None:
        view.page().runJavaScript("window.__snap()", lambda data: save(name, data))

    def save(name: str, data) -> None:
        if isinstance(data, str) and data.startswith("data:image"):
            png = base64.b64decode(data.split(",", 1)[1])
            (OUT / f"tears-{name}.png").write_bytes(png)
            log("saved tears-" + name)
        else:
            log("fail " + name)
        state["idx"] += 1
        QTimer.singleShot(250, step)

    def finish() -> None:
        log("finish")
        LOG.flush()
        os._exit(0)

    QTimer.singleShot(1500, poll_loaded)
    QTimer.singleShot(70000, finish)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
