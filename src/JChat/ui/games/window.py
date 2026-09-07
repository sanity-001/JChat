"""和伙伴一起玩游戏：GameDialog（Q 版 UI）+ 游戏注册表（接缝：新游戏加一行注册）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from JChat.ui.widgets import IdleAvatar

BOARD_PX = 480
CELL = BOARD_PX / 16  # 15 线 + 边距
MARGIN = CELL

GAMES: dict[str, type] = {}


def register(name: str, cls: type) -> None:
    GAMES[name] = cls


def open_game_window(controller, name: str = "五子棋") -> None:
    if getattr(controller, "game_window", None) is None:
        controller.game_window = GameDialog(controller, name)
    controller.game_window.show()
    controller.game_window.raise_()


class GomokuBoard(QWidget):
    """Q 版五子棋棋盘：奶油底 + 柔和网格 + 玻璃光泽棋子。"""

    def __init__(self, on_user_move, size=15, parent=None):
        super().__init__(parent)
        self._size = size
        self._on_user_move = on_user_move  # callable(col, row)
        self._game = None  # 由外部注入 Gomoku 实例
        self.setFixedSize(BOARD_PX, BOARD_PX)

    def attach(self, game) -> None:
        self._game = game
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._game is None:
            return
        col = round((event.position().x() - MARGIN) / (CELL))
        row = round((event.position().y() - MARGIN) / (CELL))
        if 0 <= col < self._size and 0 <= row < self._size:
            self._on_user_move(col, row)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 底
        p.setBrush(QColor("#FFF8F0"))
        p.setPen(QPen(QColor("#F0C9A8"), 6))
        p.drawRoundedRect(2, 2, BOARD_PX - 4, BOARD_PX - 4, 22, 22)
        # 网格
        pen = QPen(QColor("#D9B08C"), 1)
        p.setPen(pen)
        n = self._size
        for i in range(n):
            x = MARGIN + i * CELL
            p.drawLine(int(x), int(MARGIN), int(x), int(MARGIN + (n - 1) * CELL))
            p.drawLine(int(MARGIN), int(x), int(MARGIN + (n - 1) * CELL), int(x))
        # 星位
        p.setBrush(QColor("#C99A6E"))
        for cx, cy in ((3, 3), (11, 3), (3, 11), (11, 11), (7, 7)):
            x, y = MARGIN + cx * CELL, MARGIN + cy * CELL
            p.drawEllipse(int(x - 3), int(y - 3), 6, 6)
        # 棋子（Q 版玻璃光泽）
        if self._game is not None:
            for c, r, who in self._game.history:
                x, y = MARGIN + c * CELL, MARGIN + r * CELL
                radius = CELL * 0.42
                base = QColor("#FF9EB5") if who == 2 else QColor("#5B5B6B")
                p.setPen(QPen(QColor("#FFFFFF"), 1))
                p.setBrush(base)
                p.drawEllipse(int(x - radius), int(y - radius), int(radius * 2), int(radius * 2))
                # 高光
                p.setBrush(QColor(255, 255, 255, 140))
                p.setPen(QPen(Qt.NoPen))
                p.drawEllipse(
                    int(x - radius * 0.45), int(y - radius * 0.55),
                    int(radius * 0.55), int(radius * 0.45),
                )
        p.end()


class GameDialog(QDialog):
    """游戏主窗：左棋盘 + 右侧伙伴面板（头像/台词/比分/操作）。"""

    def __init__(self, controller, game: str = "五子棋", parent=None):
        super().__init__(parent)
        self.controller = controller
        self.game_name = game
        from JChat.ui.games.gomoku import Gomoku

        self.g = Gomoku()
        nickname = controller.config["companion"]["nickname"]
        self.setWindowTitle(f"🎮 和{nickname}一起玩{game}")
        self.setStyleSheet("QDialog { background:#FFF6EC; }")

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        self.board_view = GomokuBoard(self._on_user_move)
        self.board_view.attach(self.g)
        root.addWidget(self.board_view)

        side = QVBoxLayout()
        side.setSpacing(10)
        self.avatar = IdleAvatar(size=96, row=4, frames=5)  # 开心喘气行动画
        side.addWidget(self.avatar, alignment=Qt.AlignHCenter)
        name = QLabel(nickname)
        name.setStyleSheet("font-weight:700; font-size:16px; color:#B0567A;")
        side.addWidget(name, alignment=Qt.AlignHCenter)

        self.bubble = QLabel("要来一局吗？我先手让你～")
        self.bubble.setWordWrap(True)
        self.bubble.setAlignment(Qt.AlignCenter)
        self.bubble.setStyleSheet(
            "background:#DFF5E1;color:#3A5A40;border-radius:14px;padding:10px;font-size:13px;"
        )
        self.bubble.setFixedWidth(190)
        side.addWidget(self.bubble)

        self.score = QLabel("比分  你 0 : 0 她")
        self.score.setStyleSheet("color:#8A6D3B; font-size:13px;")
        side.addWidget(self.score, alignment=Qt.AlignHCenter)
        self._user_wins = 0
        self._ai_wins = 0

        btn_restart = QPushButton("🔄 重新开始")
        btn_restart.setCursor(Qt.PointingHandCursor)
        btn_restart.setStyleSheet(
            "QPushButton{background:#FFD9E8;color:#B0567A;border:none;border-radius:14px;"
            "padding:8px;font-size:13px;font-weight:600;}"
        )
        btn_restart.clicked.connect(self._restart)
        side.addWidget(btn_restart)

        btn_undo = QPushButton("↩️ 悔棋")
        btn_undo.setCursor(Qt.PointingHandCursor)
        btn_undo.setStyleSheet(btn_restart.styleSheet())
        btn_undo.clicked.connect(self._undo)
        side.addWidget(btn_undo)

        root.addLayout(side)

    # ------------------------------------------------------------ 落子流程
    def _on_user_move(self, col: int, row: int) -> None:
        if not self.g.place(col, row, 1):
            return
        self.board_view.update()
        if self.g.check_win(col, row):
            self._end(user_win=True)
            return
        if self.g.full():
            self._end(user_win=None)
            return
        self._ai_turn()

    def _ai_turn(self) -> None:
        companion = getattr(self.controller, "companion", None)
        if companion:
            companion.flash_expression("thinking", 15000)
        self.bubble.setText("让我想想……")
        self.controller.queue.submit(0, self._ai_worker)

    def _ai_worker(self) -> None:
        """worker 线程：LLM 决策（失败/非法→本地启发式保底）。"""

        from JChat.agent.extractor import _parse_json
        from JChat.ui.games.gomoku import AI

        quip, move = "", None
        if self.controller.llm is not None:
            nickname = self.controller.config["companion"]["nickname"]
            persona = self.controller.config["companion"]["persona"][:160]
            system = (
                f"你是{nickname}。{persona}\n"
                "你们正在下五子棋（15×15，你执粉子）。\n"
                + self.g.serialize()
                + '\n\n只输出 JSON：{"col": 数字, "row": 数字, "quip": "一句不超过20字的你的口吻的话"}\n'
                "col=列(1-15)，row=行(1-15)，只能下在空位。策略：能连五就赢，能堵对方四连就堵，否则靠近已有棋子扩展。"
            )
            try:
                resp = self.controller.llm.chat(
                    [{"role": "system", "content": system}], max_tokens=200
                )
                data = _parse_json(resp["choices"][0]["message"]["content"] or "{}")
                col, row = int(data.get("col", -1)) - 1, int(data.get("row", -1)) - 1
                quip = str(data.get("quip", ""))[:40]
                if 0 <= col < 15 and 0 <= row < 15 and self.g.board[row][col] == 0:
                    move = (col, row)
            except Exception:  # noqa: BLE001
                pass
        if move is None:
            move = self.g.heuristic_move()
            quip = quip or "哼，看我这手！"
        col, row = move
        self.controller.ui_task.emit(lambda: self._apply_ai_move(col, row, quip, AI))

    def _apply_ai_move(self, col: int, row: int, quip: str, who: int) -> None:
        from JChat.ui.games.gomoku import AI

        _ = who
        self.g.place(col, row, AI)
        self.board_view.update()
        if quip:
            self.bubble.setText(quip)
        if self.g.check_win(col, row):
            self._end(user_win=False)
            return
        if self.g.full():
            self._end(user_win=None)

    # ------------------------------------------------------------ 结果与操作
    def _end(self, user_win: bool | None) -> None:
        companion = getattr(self.controller, "companion", None)
        if user_win is True:
            self._user_wins += 1
            self.bubble.setText("呜……你赢了！算你厉害，下局我一定翻盘！")
            if companion:
                companion.flash_expression("sad")
        elif user_win is False:
            self._ai_wins += 1
            self.bubble.setText("嘻嘻嘻，本小姐赢啦！奖励你一颗烤土豆～")
            if companion:
                companion.flash_expression("celebrate")
        else:
            self.bubble.setText("平局……下局不许放水！")
        self.score.setText(f"比分  你 {self._user_wins} : {self._ai_wins} 她")

    def _restart(self) -> None:
        from JChat.ui.games.gomoku import Gomoku

        self.g = Gomoku()
        self.board_view.attach(self.g)
        self.bubble.setText("再来！这次我不会手软～")

    def _undo(self) -> None:
        if self.g.undo_last() and self.g.history and self.g.history[-1][2] == 2:
            self.g.undo_last()  # 撤掉 AI 那手，轮回用户
        self.board_view.update()
        self.bubble.setText("行吧，悔就悔了，就这一局哦。")
