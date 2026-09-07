"""五子棋：棋盘状态 + 胜负判定 + 本地启发式（LLM 不可用/非法着时的保底）。"""

from __future__ import annotations

SIZE = 15
EMPTY, USER, AI = 0, 1, 2


class Gomoku:
    def __init__(self) -> None:
        self.board = [[EMPTY] * SIZE for _ in range(SIZE)]
        self.history: list[tuple[int, int, int]] = []  # (col, row, who)

    def place(self, col: int, row: int, who: int) -> bool:
        if not (0 <= col < SIZE and 0 <= row < SIZE) or self.board[row][col] != EMPTY:
            return False
        self.board[row][col] = who
        self.history.append((col, row, who))
        return True

    def undo_last(self) -> bool:
        """悔一手（供悔棋按钮逐手回退）。"""
        if not self.history:
            return False
        col, row, _ = self.history.pop()
        self.board[row][col] = EMPTY
        return True

    def check_win(self, col: int, row: int) -> bool:
        who = self.board[row][col]
        if who == EMPTY:
            return False
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            count = 1
            for sign in (1, -1):
                x, y = col + dx * sign, row + dy * sign
                while 0 <= x < SIZE and 0 <= y < SIZE and self.board[y][x] == who:
                    count += 1
                    x, y = x + dx * sign, y + dy * sign
            if count >= 5:
                return True
        return False

    def full(self) -> bool:
        return len(self.history) >= SIZE * SIZE

    def serialize(self) -> str:
        lines = ["棋盘 15×15，col=列(1-15 从左到右)，row=行(1-15 从上到下)。已有落子："]
        stones = [f"col={c + 1},row={r + 1}：{'你' if w == AI else '用户'}" for c, r, w in self.history]
        lines += stones if stones else ["（空盘，你是先手）"]
        return "\n".join(lines)

    def heuristic_move(self) -> tuple[int, int]:
        """保底着法：进攻/防守打分 + 中心偏好。"""
        best, best_score = (SIZE // 2, SIZE // 2), -1.0
        for r in range(SIZE):
            for c in range(SIZE):
                if self.board[r][c] != EMPTY:
                    continue
                score = 0.9 * self._score_at(c, r, AI) + self._score_at(c, r, USER)
                score += 0.05 * (SIZE - (abs(c - 7) + abs(r - 7)))
                if score > best_score:
                    best, best_score = (c, r), score
        return best

    def _score_at(self, col: int, row: int, who: int) -> float:
        """假设 who 落子在 (col,row) 后，四方向最长连子数之和。"""
        total = 0.0
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            count = 1
            for sign in (1, -1):
                x, y = col + dx * sign, row + dy * sign
                while 0 <= x < SIZE and 0 <= y < SIZE and self.board[y][x] == who:
                    count += 1
                    x, y = x + dx * sign, y + dy * sign
            total += count
        return total
