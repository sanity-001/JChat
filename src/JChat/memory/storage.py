"""SQLite persistence: the source of truth, one file, zero servers.

Tables:
  docs       — ingested documents (path, content fingerprint, plain text)
  entities   — node registry (node_id = 'EntityType::Name', unique)
  doc_entities — junction (node_id, doc_id) used for per-doc pruning
  relations  — labeled edges with the doc that produced them
  memories   — short/long-term memory rows (scope, importance, decay state)
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS entities (
    node_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    name TEXT NOT NULL,
    doc_id INTEGER,
    importance REAL NOT NULL DEFAULT 1.0
);
CREATE TABLE IF NOT EXISTS doc_entities (
    node_id TEXT NOT NULL REFERENCES entities(node_id),
    doc_id INTEGER NOT NULL REFERENCES docs(id),
    PRIMARY KEY (node_id, doc_id)
);
CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    head TEXT NOT NULL,
    rel_type TEXT NOT NULL,
    tail TEXT NOT NULL,
    doc_id INTEGER REFERENCES docs(id),
    weight REAL NOT NULL DEFAULT 1.0
);
CREATE TABLE IF NOT EXISTS memories (
    memory_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    content TEXT NOT NULL,
    entities TEXT NOT NULL DEFAULT '[]',
    importance REAL NOT NULL DEFAULT 1.0,
    access_count INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    last_access_at REAL NOT NULL,
    score REAL NOT NULL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_relations_head ON relations(head);
CREATE INDEX IF NOT EXISTS idx_relations_tail ON relations(tail);
CREATE INDEX IF NOT EXISTS idx_memories_score ON memories(score);
"""


def content_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


class SQLiteStore:
    def __init__(self, path: str | None = None):
        self.db_path = path or ":memory:"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def commit(self) -> None:
        self.conn.commit()

    # ---------------------------------------------------------------- documents
    def upsert_doc(self, path: str, text: str) -> tuple[int, bool]:
        """Insert a doc or refresh it; returns (doc_id, changed)."""
        h = content_fingerprint(text)
        now = time.time()
        row = self.conn.execute("SELECT id, content_hash FROM docs WHERE path = ?", (path,)).fetchone()
        if row and row[1] == h:
            return row[0], False
        if row:
            self.conn.execute(
                "UPDATE docs SET content_hash=?, text=?, updated_at=? WHERE id=?",
                (h, text, now, row[0]),
            )
            doc_id = row[0]
        else:
            cur = self.conn.execute(
                "INSERT INTO docs(path, content_hash, text, created_at, updated_at) VALUES (?,?,?,?,?)",
                (path, h, text, now, now),
            )
            doc_id = cur.lastrowid
        self.conn.commit()
        return doc_id, True

    def delete_doc(self, path: str) -> int | None:
        row = self.conn.execute("SELECT id FROM docs WHERE path = ?", (path,)).fetchone()
        if not row:
            return None
        doc_id = row[0]
        self.conn.execute("DELETE FROM doc_entities WHERE doc_id=?", (doc_id,))
        self.conn.execute("DELETE FROM relations WHERE doc_id=?", (doc_id,))
        self.conn.execute("DELETE FROM docs WHERE id=?", (doc_id,))
        self._prune_orphan_entities()
        self.conn.commit()
        return doc_id

    def docs(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, path, content_hash, created_at, updated_at FROM docs ORDER BY id"
        ).fetchall()
        return [
            dict(
                zip(
                    ("id", "path", "content_hash", "created_at", "updated_at"),
                    r,
                    strict=True,
                )
            )
            for r in rows
        ]

    def doc_text(self, doc_id: int) -> str | None:
        row = self.conn.execute("SELECT text FROM docs WHERE id=?", (doc_id,)).fetchone()
        return row[0] if row else None

    def all_doc_texts(self) -> list[tuple[int, str]]:
        return self.conn.execute("SELECT id, text FROM docs ORDER BY id").fetchall()

    # ------------------------------------------------------------- entities/graph
    def save_node(self, node_id: str, label: str, name: str, doc_id: int | None, importance: float) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO entities(node_id, label, name, doc_id, importance) VALUES (?,?,?,?,?)",
            (node_id, label, name, doc_id, importance),
        )
        if doc_id is not None:
            self.conn.execute(
                "INSERT OR IGNORE INTO doc_entities(node_id, doc_id) VALUES (?,?)",
                (node_id, doc_id),
            )

    def save_relation(self, head: str, rel_type: str, tail: str, doc_id: int | None, weight: float) -> None:
        exists = self.conn.execute(
            "SELECT id FROM relations WHERE head=? AND rel_type=? AND tail=? AND doc_id IS ?",
            (head, rel_type, tail, doc_id),
        ).fetchone()
        if not exists:
            self.conn.execute(
                "INSERT INTO relations(head, rel_type, tail, doc_id, weight) VALUES (?,?,?,?,?)",
                (head, rel_type, tail, doc_id, weight),
            )
            for nid in (head, tail):
                self.conn.execute(
                    "INSERT OR IGNORE INTO entities(node_id, label, name, doc_id, importance) "
                    "VALUES (?,?,?,?,1.0)",
                    (nid, nid.split("::", 1)[0], nid.split("::", 1)[-1], doc_id),
                )
                self.conn.execute(
                    "INSERT OR IGNORE INTO doc_entities(node_id, doc_id) VALUES (?,?)",
                    (nid, doc_id),
                )

    def clear_doc_graph(self, doc_id: int) -> None:
        self.conn.execute("DELETE FROM relations WHERE doc_id=?", (doc_id,))
        self.conn.execute("DELETE FROM doc_entities WHERE doc_id=?", (doc_id,))
        self._prune_orphan_entities()

    def _prune_orphan_entities(self) -> None:
        self.conn.execute(
            "DELETE FROM entities WHERE node_id NOT IN (SELECT node_id FROM doc_entities) "
            "AND node_id NOT IN (SELECT head FROM relations) "
            "AND node_id NOT IN (SELECT tail FROM relations)"
        )

    def load_graph_rows(self) -> tuple[list[tuple], list[tuple]]:
        nodes = self.conn.execute("SELECT node_id, label, name, doc_id, importance FROM entities").fetchall()
        edges = self.conn.execute("SELECT head, rel_type, tail, doc_id, weight FROM relations").fetchall()
        return nodes, edges

    # ------------------------------------------------------------------ memories
    def save_memory(
        self,
        memory_id: str,
        scope: str,
        content: str,
        entities: list[str],
        importance: float,
        created_at: float | None = None,
        last_access_at: float | None = None,
        access_count: int = 0,
        score: float = 0.0,
    ) -> None:
        now = time.time()
        self.conn.execute(
            "INSERT OR REPLACE INTO memories(memory_id, scope, content, entities, importance,"
            " access_count, created_at, last_access_at, score) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                memory_id,
                scope,
                content,
                json.dumps(entities),
                importance,
                access_count,
                created_at or now,
                last_access_at or now,
                score,
            ),
        )
        self.conn.commit()

    def get_memory(self, memory_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM memories WHERE memory_id=?", (memory_id,)).fetchone()
        return self._memory_row(row) if row else None

    def touch_memory(self, memory_id: str, score: float) -> None:
        self.conn.execute(
            "UPDATE memories SET access_count=access_count+1, last_access_at=?, score=? WHERE memory_id=?",
            (time.time(), score, memory_id),
        )
        self.conn.commit()

    def set_memory_scope(self, memory_id: str, scope: str, score: float) -> None:
        self.conn.execute("UPDATE memories SET scope=?, score=? WHERE memory_id=?", (scope, score, memory_id))
        self.conn.commit()

    def update_memory_score(self, memory_id: str, score: float) -> None:
        self.conn.execute("UPDATE memories SET score=? WHERE memory_id=?", (score, memory_id))
        self.conn.commit()

    def list_memories(self, scope: str | None = None) -> list[dict]:
        if scope:
            rows = self.conn.execute(
                "SELECT * FROM memories WHERE scope=? ORDER BY score DESC", (scope,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM memories ORDER BY score DESC").fetchall()
        return [self._memory_row(r) for r in rows]

    def delete_memory(self, memory_id: str) -> None:
        self.conn.execute("DELETE FROM memories WHERE memory_id=?", (memory_id,))
        self.conn.commit()

    def delete_memories(self, memory_ids: list[str]) -> None:
        for mid in memory_ids:
            self.delete_memory(mid)

    def _memory_row(self, row: tuple) -> dict:
        return {
            "memory_id": row[0],
            "scope": row[1],
            "content": row[2],
            "entities": json.loads(row[3]),
            "importance": row[4],
            "access_count": row[5],
            "created_at": row[6],
            "last_access_at": row[7],
            "score": row[8],
        }
