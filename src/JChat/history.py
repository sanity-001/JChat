"""聊天历史持久化（票据 Q11 B）：SQLite chats 表，跨会话可回溯、供抽取。线程安全（复用 store 锁）。"""

from __future__ import annotations

import time


class ChatHistory:
    def __init__(self, store, session_id: str):
        self.store = store
        self.conn = store.conn
        self.session_id = session_id
        with self.store._lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chats_session ON chats(session_id);
                """
            )
            self.conn.commit()

    def add(self, role: str, content: str) -> None:
        with self.store._lock:
            self.conn.execute(
                "INSERT INTO chats(session_id, role, content, created_at) VALUES (?,?,?,?)",
                (self.session_id, role, content, time.time()),
            )
            self.conn.commit()

    def transcript(self) -> list[dict]:
        with self.store._lock:
            rows = self.conn.execute(
                "SELECT role, content, created_at FROM chats WHERE session_id=? ORDER BY id",
                (self.session_id,),
            ).fetchall()
        return [{"role": r[0], "content": r[1], "created_at": r[2]} for r in rows]
