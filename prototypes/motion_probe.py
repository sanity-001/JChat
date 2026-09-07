"""验证 motion 是否加载/播放：dump definitions + play + 采样 Param100。"""

from __future__ import annotations

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
LOG = open(r"C:\Users\RUANZH~1\AppData\Local\Temp\opencode\motion_probe.log", "w", encoding="utf-8")


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

    state = {"phase": 0}

    def poll_loaded(attempt: int = 0) -> None:
        view.page().runJavaScript(
            "window.__modelLoaded ? 'ok' : 'ERR:' + window.__loadError",
            lambda r: _on_load(r, attempt),
        )

    def _on_load(r, attempt) -> None:
        if r == "ok":
            log("loaded")
            inspect()
        elif attempt < 40:
            QTimer.singleShot(500, lambda: poll_loaded(attempt + 1))
        else:
            log("load-fail " + str(r))
            finish()

    def inspect() -> None:
        js = """
        (function(){
            var m = window.__model;
            var mm = m.internalModel.motionManager;
            var out = {};
            try { out.defs = Object.keys(mm.definitions || {}); } catch(e){ out.defs = 'EX:'+e.message; }
            try { out.settings = JSON.stringify((m.internalModel.settings.motions || []).map(function(mt){return mt.Group+'/'+mt.Name+'/'+mt.File;})); } catch(e){ out.settings='EX'; }
            try { var r = m.motion('emotion', 0); out.play = r ? 'ok' : 'none'; } catch(e){ out.play = 'EX:'+e.message; }
            return JSON.stringify(out);
        })();
        """
        view.page().runJavaScript(js, lambda r: (log("INSP " + str(r)[:800]), QTimer.singleShot(600, sample1)))

    def sample1() -> None:
        view.page().runJavaScript("window.__probeRead('Param100')", lambda r: (log("P100@0.6s " + str(r)[:120]), QTimer.singleShot(700, sample2)))

    def sample2() -> None:
        view.page().runJavaScript("window.__probeRead('Param100')", lambda r: (log("P100@1.3s " + str(r)[:120]), QTimer.singleShot(900, sample3)))

    def sample3() -> None:
        view.page().runJavaScript("window.__probeRead('Param100')", lambda r: log("P100@2.2s " + str(r)[:120]))
        QTimer.singleShot(600, finish)

    def finish() -> None:
        log("finish")
        LOG.flush()
        os._exit(0)

    QTimer.singleShot(1500, poll_loaded)
    QTimer.singleShot(60000, finish)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
