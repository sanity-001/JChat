"""应用入口与整合：配置、存储、上下文、worker 队列、会话、主动搭话、会话抽取。"""

from __future__ import annotations

import logging
import random
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

logger = logging.getLogger("JChat")


def _ui(fn) -> None:
    """从工作线程安全地调度 UI 更新到主线程。"""
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
        self.pending_proactive: str | None = None
        self.session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.history = ChatHistory(self.store.conn, self.session_id)

    # ------------------------------------------------------------ companion
    def open_chat(self) -> None:
        if self.chat_window is not None:
            self.chat_window.show()
            self.chat_window.raise_()
            return
        win = ChatWindow(self.config, memory_count_fn=self.memory_count, parent=None)
        win.send_requested.connect(self.on_send)
        win.closed.connect(self.on_session_close)
        win.show()
        self.chat_window = win
        self.companion.hide()

    def close_chat(self) -> None:
        if self.chat_window is not None:
            self.chat_window.close()

    def on_session_close(self) -> None:
        self.companion.show()
        turns = len(self.window_msgs) // 2
        if self.llm and turns >= self.config["memory"]["extraction_min_turns"]:
            self.queue.submit(2, self._extract_async)
        self.chat_window = None

    def memory_count(self) -> int:
        return len(self.memory.state())

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.config, self.memory, parent=self.companion)
        if dlg.exec():
            logger.info("设置已保存")

    # ------------------------------------------------------------ chat turn
    def on_send(self, text: str) -> None:
        if self.chat_window is None:
            return
        self.chat_window.add_user_message(text)
        self.history.add("user", text)
        self.window_msgs.append({"role": "user", "content": text})
        self.chat_window.set_busy(True)
        self.ctx.cancel.clear()

        if self.llm is None:
            self._finish_turn("未配置 API Key：请编辑 config.private.json 填入 llm.api_key 后重启。")
            return
        self.queue.submit(0, lambda: self._run_worker_turn(text))

    def _run_worker_turn(self, text: str) -> None:
        card_refs: dict[int, object] = {}
        ev_seq = [0]

        def on_tool_event(ev) -> None:
            idx = ev_seq[0]
            ev_seq[0] += 1
            _ui(lambda: card_refs.__setitem__(idx, self.chat_window.add_tool_card(ev.name, "运行中…")))

        turn_ctx = AgentContext(
            config=self.config,
            llm=self.llm,
            memory=self.memory,
            retriever=self.retriever,
            cancel=self.ctx.cancel,
            on_tool_event=on_tool_event,
        )
        try:
            reply, events = run_turn(text, self.window_msgs, turn_ctx)
        except Exception as e:  # noqa: BLE001
            logger.exception("turn failed")
            reply = f"（出错了：{type(e).__name__}: {e}）"
            events = []

        def finish() -> None:
            if self.chat_window is None:
                return
            for i, ev in enumerate(events):
                card = card_refs.get(i)
                if card is not None:
                    status = "完成" if ev.status == "done" else "失败"
                    self.chat_window.update_tool_card(card, status, ev.output_preview)
            self._finish_turn(reply)

        _ui(finish)

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

    # ------------------------------------------------------------ extraction
    def _extract_async(self) -> None:
        transcript = self.history.transcript()
        if not transcript:
            return
        result = extract_session(transcript, self.memory, self.store, self.llm, cfg=self.config)
        self.memory.consolidate()
        if result:
            _ui(lambda: self.companion.show_bubble(f"🧠 已记住 {result['facts']} 件新事"))

    # ------------------------------------------------------------ proactive
    def schedule_proactive(self) -> None:
        if not self.config["companion"]["random_chat"]:
            return
        interval = (
            random.randint(
                self.config["companion"]["proactive_min"], self.config["companion"]["proactive_max"]
            )
            * 60
            * 1000
        )
        QTimer.singleShot(interval, self._proactive_tick)

    def _proactive_tick(self) -> None:
        if self._proactive_suppressed():
            self.schedule_proactive()
            return
        if self.llm is None:
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
        return self.companion.is_chat_window_open() and self.chat_window is not None

    def _proactive_worker(self) -> None:
        from JChat.agent.prompts import build_memory_card, build_system_prompt

        card = build_memory_card("", self.memory, self.retriever, "", self.config)
        system = build_system_prompt(self.config["companion"]["persona"], card)
        try:
            text = self.llm.complete(
                [
                    {
                        "role": "system",
                        "content": system + "\n\n现在你主动对用户说一句话（不超过 40 字，自然口语）。",
                    },
                    {"role": "user", "content": "（请主动搭话）"},
                ],
                max_tokens=128,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("proactive failed: %s", e)
            self.schedule_proactive()
            return
        self.pending_proactive = text.strip()
        _ui(lambda: self.companion.show_bubble(self.pending_proactive))
        self.schedule_proactive()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("JChat %s 启动", __version__)
    ensure_default_configs()
    config = load_config()
    app = QApplication([])
    controller = App(config)

    companion = CompanionWindow(
        config,
        on_open_chat=controller.open_chat,
        on_settings=controller.open_settings,
        on_proactive=controller._proactive_tick,
    )
    controller.companion = companion
    controller.schedule_proactive()
    import sys

    sys.exit(app.exec())
