"""hitTest 网格探测：验证 HitAreas 坐标。"""

from __future__ import annotations

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
LOG = open(r"C:\Users\RUANZH~1\AppData\Local\Temp\opencode\hittest.log", "w", encoding="utf-8")


def log(msg) -> None:
    LOG.write(msg + "\n")
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

    def poll_loaded(attempt: int = 0) -> None:
        view.page().runJavaScript(
            "window.__modelLoaded ? 'ok' : 'ERR:' + window.__loadError",
            lambda r: _on_load(r, attempt),
        )

    def _on_load(r, attempt) -> None:
        if r == "ok":
            log("loaded")
            QTimer.singleShot(800, run_grid)
        elif attempt < 40:
            QTimer.singleShot(500, lambda: poll_loaded(attempt + 1))
        else:
            log("load-fail " + str(r))
            finish()

    def run_grid() -> None:
        js = """
        (function(){
            var m = window.__model || null;
            if (!m) return JSON.stringify({err:'no model'});
            var im = m.internalModel;
            var out = {};
            try { out.sx = m.scale.x; } catch(e){ out.sx='EX'; }
            try { out.px = m.position.x; } catch(e){ out.px='EX'; }
            try { out.py = m.position.y; } catch(e){ out.py='EX'; }
            try { out.w = im.originalWidth; } catch(e){ out.w='EX'; }
            try { out.h = im.originalHeight; } catch(e){ out.h='EX'; }
            try { out.mx = m.x; } catch(e){ out.mx='EX'; }
            try { out.my = m.y; } catch(e){ out.my='EX'; }
            return JSON.stringify(out);
        })();
        """
        view.page().runJavaScript(js, lambda r: log("SCALE\n" + str(r)[:1200]))
        QTimer.singleShot(1500, finish)

    def finish() -> None:
        log("finish")
        LOG.flush()
        os._exit(0)

    QTimer.singleShot(1500, poll_loaded)
    QTimer.singleShot(60000, finish)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
