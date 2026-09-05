"""应用入口与整合：配置、存储、上下文、worker 队列、会话（悬停+大窗共享）、主动搭话、会话抽取。"""

from __future__ import annotations

import logging
import random
import sys
from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from JChat import __version__
from JChat.agent.extractor import extract_session
from JChat.agent.loop import AgentContext, run_turn
from JChat.config import PROJECT_ROOT, ensure_default_configs, load_config
from JChat.history import ChatHistory
from JChat.llm.client import LLMClient
from JChat.memory.builder import KnowledgeGraphBuilder
from JChat.memory.memory import AgentMemory
from JChat.memory.ontology import default_tech
from JChat.memory.retriever import HybridRetriever
from JChat.memory.storage import SQLiteStore
from JChat.memory.vector import build_vector_index
from JChat.queue import LLMQueue
from JChat.ui.chat_window import ChatWindow
from JChat.ui.companion_window import CompanionWindow
from JChat.ui.settings_dialog import SettingsDialog
from JChat.ui.theme import QSS

logger = logging.getLogger("JChat")

SESSION_END_MS = 30_000


def _ui(fn) -> None:
    QTimer.singleShot(0, fn)


class App:
    def __init__(self, config: dict):
        self.config = config
        self.store = SQLiteStore(str(PROJECT_ROOT / "jchat.sqlite"))
        self.memory = AgentMemory(
            self.store,
            working_window=config["memory"]["working_window"],
            decay_rate=config["memory"]["decay_rate"],
        )
        self.builder = KnowledgeGraphBuilder(ontology=default_tech(), store=self.store)
        self.retriever = HybridRetriever(self.builder.graph, build_vector_index(self.store.all_doc_texts()))
        self.llm = LLMClient(config) if config["llm"]["api_key"] else None
        self.ctx = AgentContext(config=config, llm=self.llm, memory=self.memory, retriever=self.retriever)
        self.queue = LLMQueue(workers=1)
        self.window_msgs: list[dict] = []
        self.chat_window: ChatWindow | None = None
        self.companion: CompanionWindow | None = None
        self.through_hover = False
        self.session_id = self._new_session_id()
        self.history = ChatHistory(self.store, self.session_id)
        self._session_timer = QTimer()
        self._session_timer.setSingleShot(True)
        self._session_timer.timeout.connect(self._on_session_end)

    @staticmethod
    def _new_session_id() -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    # ------------------------------------------------------------ companion wiring
    def attach_companion(self, companion: CompanionWindow) -> None:
        self.companion = companion
        companion.send_requested.connect(lambda t: self.on_send(t, via="hover"))
        companion.open_chat_requested.connect(self.open_big_window)
        companion.hover_collapsed.connect(self._arm_session_end)

    # ------------------------------------------------------------ big window
    def open_big_window(self) -> None:
        if self.chat_window is not None:
            self.chat_window.show()
            self.chat_window.raise_()
            return
        win = ChatWindow(self.config, memory_count_fn=self.memory_count, parent=None)
        win.send_requested.connect(lambda t: self.on_send(t, via="big"))
        win.closed.connect(self.on_big_window_close)
        win.load_history(self.window_msgs)
        win.show()
        self.chat_window = win
        if self.companion:
            self.companion.set_chat_window_open(True)

    def on_big_window_close(self) -> None:
        if self.companion:
            self.companion.set_chat_window_open(False)
        self.chat_window = None
        self._on_session_end()

    # ------------------------------------------------------------ chat turn
    def on_send(self, text: str, via: str = "hover") -> None:
        self.through_hover = via == "hover"
        self._session_timer.stop()
        if via == "big" and self.chat_window:
            self.chat_window.add_user_message(text)
        self.history.add("user", text)
        self.window_msgs.append({"role": "user", "content": text})

        if via == "big" and self.chat_window:
            self.chat_window.set_busy(True)
        if self.llm is None:
            self._finish_turn("未配置 API Key：请编辑 config.private.json 填入 llm.api_key 后重启。")
            return
        self.ctx.cancel.clear()
        self.queue.submit(0, lambda: self._run_worker_turn(text))

    def _run_worker_turn(self, text: str) -> None:
        proactive = self.companion.pending_proactive if self.companion else None
        card_refs: dict[int, object] = {}
        ev_seq = [0]

        def on_tool_event(ev) -> None:
            idx = ev_seq[0]
            ev_seq[0] += 1
            if self.through_hover:
                return
            _ui(lambda: card_refs.__setitem__(idx, self.chat_window.add_tool_card(ev.name, "运行中…")))

        turn_ctx = AgentContext(
            config=self.config, llm=self.llm, memory=self.memory, retriever=self.retriever,
            cancel=self.ctx.cancel, on_tool_event=on_tool_event,
        )
        try:
            reply, events = run_turn(text, self.window_msgs, turn_ctx, proactive_text=proactive)
        except Exception as e:  # noqa: BLE001
            logger.exception("turn failed")
            reply = f"（出错了：{type(e).__name__}: {e}）"
            events = []

        def finish() -> None:
            if self.through_hover and self.companion:
                self._record_reply(reply)
                self.companion.show_reply(reply, events)
                self._arm_session_end()
            elif self.chat_window:
                for i, ev in enumerate(events):
                    card = card_refs.get(i)
                    if card is not None:
                        status = "完成" if ev.status == "done" else "失败"
                        self.chat_window.update_tool_card(card, status, ev.output_preview)
                self._finish_turn(reply)

        _ui(finish)

    def _record_reply(self, reply: str) -> None:
        self.window_msgs.append({"role": "assistant", "content": reply})
        self.history.add("assistant", reply)
        self._trim_window()

    def _finish_turn(self, reply: str) -> None:
        if self.chat_window is None:
            return
        self.window_msgs.append({"role": "assistant", "content": reply})
        self.history.add("assistant", reply)
        self.chat_window.add_companion_message(reply)
        self.chat_window.set_busy(False)
        self._trim_window()

    def _trim_window(self) -> None:
        limit = self.config["memory"]["window_turns"] * 2
        if len(self.window_msgs) > limit:
            self.window_msgs = self.window_msgs[-limit:]

    # ------------------------------------------------------------ session lifecycle
    def _arm_session_end(self) -> None:
        self._session_timer.start(SESSION_END_MS)

    def _on_session_end(self) -> None:
        self._session_timer.stop()
        turns = len(self.window_msgs) // 2
        if turns > 0 and self.llm:
            transcript = list(self.history.transcript())
            if turns >= self.config["memory"]["extraction_min_turns"]:
                self.queue.submit(2, lambda: self._extract(transcript))
        self._reset_session()

    def _extract(self, transcript: list[dict]) -> None:
        result = extract_session(transcript, self.memory, self.store, self.llm, cfg=self.config)
        self.memory.consolidate()
        if result:
            logger.info("会话抽取完成：%s", result)

    def _reset_session(self) -> None:
        self.window_msgs = []
        self.session_id = self._new_session_id()
        self.history = ChatHistory(self.store, self.session_id)
        if self.companion:
            self.companion.pending_proactive = None

    def memory_count(self) -> int:
        return len(self.memory.state())

    def open_settings(self) -> None:
        if self.companion is None:
            return
        dlg = SettingsDialog(self.config, self.memory, parent=self.companion)
        if dlg.exec():
            logger.info("设置已保存")

    # ------------------------------------------------------------ proactive
    def schedule_proactive(self) -> None:
        if not self.config["companion"]["random_chat"]:
            return
        interval = random.randint(
            self.config["companion"]["proactive_min"], self.config["companion"]["proactive_max"]
        ) * 60 * 1000
        QTimer.singleShot(interval, self._proactive_tick)

    def _proactive_tick(self) -> None:
        if self.llm is None or self._proactive_suppressed():
            self.schedule_proactive()
            return
        self.queue.submit(1, self._proactive_worker)

    def _proactive_suppressed(self) -> bool:
        c = self.config["companion"]
        now = datetime.now().hour
        start, end = c["quiet_hours_start"], c["quiet_hours_end"]
        quiet = start <= now < end if start <= end else now >= start or now < end
        if quiet:
            return True
        return self.companion is not None and self.companion.chat_window_open

    def _proactive_worker(self) -> None:
        from JChat.agent.prompts import build_memory_card, build_system_prompt

        card = build_memory_card("", self.memory, self.retriever, "", self.config)
        system = build_system_prompt(self.config["companion"]["persona"], card)
        try:
            text = self.llm.complete(
                [
                    {"role": "system", "content": system
                     + "\n\n现在你主动对用户说一句话（不超过 40 字，自然口语）。"},
                    {"role": "user", "content": "（请主动搭话）"},
                ],
                max_tokens=128,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("proactive failed: %s", e)
            self.schedule_proactive()
            return
        text = (text or "").strip()
        if not text:
            self.schedule_proactive()
            return
        _ui(lambda: self.companion.show_proactive(text))
        self.schedule_proactive()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("JChat %s 启动", __version__)
    ensure_default_configs()
    config = load_config()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(QSS)

    controller = App(config)
    companion = CompanionWindow(config, on_settings=controller.open_settings)
    controller.attach_companion(companion)
    companion.show()
    controller.schedule_proactive()
    sys.exit(app.exec())
