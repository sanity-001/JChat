"""探测 v3：coreModel 原型方法 + 闭眼（数组写）+ 自动眨眼/口型可行性。"""

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
LOG = open(r"C:\Users\RUANZH~1\AppData\Local\Temp\opencode\probe4.log", "w", encoding="utf-8")


def log(msg) -> None:
    LOG.write(f"{time.time():.1f} {msg}\n")
    LOG.flush()


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
    log("start")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    app = QApplication(sys.argv)
    view = QWebEngineView()
    view.resize(360, 480)
    view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    view.page().setBackgroundColor(QColor(0, 0, 0, 0))
    model_url = "/model/" + urllib.parse.quote("vvm.model3.json")
    view.load(QUrl(f"http://127.0.0.1:{port}/web/index.html?model={model_url}"))
    view.show()

    state = {"idx": 0}

    STEPS = [
        ("insp", 'JSON.stringify({coreProto: Object.getOwnPropertyNames(Object.getPrototypeOf(model.internalModel.coreModel)).filter(function(n){return /[Tt]aram/i.test(n);}), imProto: Object.getOwnPropertyNames(Object.getPrototypeOf(model.internalModel)).filter(function(n){return /[Tt]aram/i.test(n);}), blink: !!model.internalModel.eyeBlink, lip: !!model.internalModel.lipSync, params: typeof model.internalModel.parameters})'),
        ("state", 'JSON.stringify({loaded: window.__modelLoaded, err: window.__loadError, log: window.__log.slice(-8)})'),
        ("eye0a", 'window.__probeSet2("ParamEyeLOpen", 0, "arr"); window.__probeSet2("ParamEyeROpen", 0, "arr");'),
        ("eye0b", ''),
        ("cheek", 'window.__probeSet2("ParamCheek", 1, "arr");'),
        ("reset", 'window.__probeClean();'),
    ]

    def poll_loaded(attempt: int = 0) -> None:
        view.page().runJavaScript(
            "window.__modelLoaded ? 'ok' : 'ERR:' + window.__loadError",
            lambda r: _on_load(r, attempt),
        )

    def _on_load(r, attempt) -> None:
        if r == "ok":
            log("loaded")
            step()
        elif attempt < 40:
            QTimer.singleShot(500, lambda: poll_loaded(attempt + 1))
        else:
            log("load-fail " + str(r))
            finish()

    def step() -> None:
        idx = state["idx"]
        if idx >= len(STEPS):
            log("DONE")
            finish()
            return
        name, js = STEPS[idx]
        log("run " + name)
        if js:
            view.page().runJavaScript(js, lambda r: log("ret " + name + " -> " + str(r)[:400]))
        QTimer.singleShot(900, lambda: snap(name))

    def snap(name: str) -> None:
        view.page().runJavaScript("window.__snap()", lambda img: save(name, img))

    def save(name: str, data) -> None:
        if isinstance(data, str) and data.startswith("data:image"):
            png = base64.b64decode(data.split(",", 1)[1])
            (OUT / f"v3-{name}.png").write_bytes(png)
            log("saved v3-" + name + " " + str(len(png)))
        else:
            log("fail v3-" + name + " " + str(data)[:80])
        state["idx"] += 1
        QTimer.singleShot(300, step)

    def finish() -> None:
        log("finish")
        LOG.flush()
        os._exit(0)

    QTimer.singleShot(1500, poll_loaded)
    QTimer.singleShot(60000, finish)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
