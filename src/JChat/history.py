"""聊天历史持久化（票据 Q11 B）：SQLite chats 表，跨会话可回溯、供抽取。"""

from __future__ import annotations

import time
from dataclasses import dataclass

_CHATS_SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chats_session ON chats(session_id);
"""


@dataclass
class ChatTurn:
    role: str
    content: str


class ChatHistory:
    def __init__(self, conn, session_id: str):
        conn.executescript(_CHATS_SCHEMA)
        self.conn = conn
        self.session_id = session_id

    def add(self, role: str, content: str) -> None:
        self.conn.execute(
            "INSERT INTO chats(session_id, role, content, created_at) VALUES (?,?,?,?)",
            (self.session_id, role, content, time.time()),
        )
        self.conn.commit()

    def transcript(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT role, content FROM chats WHERE session_id=? ORDER BY id", (self.session_id,)
        ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in rows]
