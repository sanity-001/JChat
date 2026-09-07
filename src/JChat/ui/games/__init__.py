"""伙伴游戏中心（接缝：新游戏 = 实现 Board + 在 GAMES 注册）。"""

from JChat.ui.games.window import GAMES, GameDialog, open_game_window  # noqa: F401

__all__ = ["GameDialog", "GAMES", "open_game_window"]


def _register_builtin() -> None:
    from JChat.ui.games.gomoku import Gomoku

    GAMES.setdefault("五子棋", Gomoku)


_register_builtin()
