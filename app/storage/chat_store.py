"""Small SQLite store for conversations and messages."""

import asyncio
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")
DEFAULT_TITLE = "New conversation"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _title_from_question(question: str) -> str:
    compact = " ".join(question.split())
    return compact[:57].rstrip() + ("…" if len(compact) > 57 else "")


class ChatStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    async def _run(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        def execute() -> T:
            with closing(self._connect()) as connection:
                with connection:
                    return operation(connection)

        return await asyncio.to_thread(execute)

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        def create(connection: sqlite3.Connection) -> None:
            connection.executescript("""
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    tool_calls_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_session_order ON messages(session_id, id);
                CREATE INDEX IF NOT EXISTS sessions_updated ON sessions(updated_at DESC);
            """)

        await self._run(create)

    async def create_session(self, title: str = DEFAULT_TITLE) -> dict[str, Any]:
        session_id, timestamp = str(uuid.uuid4()), _now()

        def create(connection: sqlite3.Connection) -> dict[str, Any]:
            connection.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, title, timestamp, timestamp),
            )
            return {"id": session_id, "title": title, "created_at": timestamp, "updated_at": timestamp, "message_count": 0, "preview": None}

        return await self._run(create)

    async def list_sessions(self) -> list[dict[str, Any]]:
        def list_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
            rows = connection.execute("""
                SELECT s.id, s.title, s.created_at, s.updated_at,
                       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count,
                       (SELECT content FROM messages m WHERE m.session_id = s.id ORDER BY m.id DESC LIMIT 1) AS preview
                FROM sessions s ORDER BY s.updated_at DESC, s.rowid DESC
            """).fetchall()
            return [dict(row) for row in rows]

        return await self._run(list_rows)

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        def get(connection: sqlite3.Connection) -> dict[str, Any] | None:
            row = connection.execute(
                "SELECT id, title, created_at, updated_at FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return dict(row) if row else None

        return await self._run(get)

    async def rename_session(self, session_id: str, title: str) -> dict[str, Any] | None:
        def rename(connection: sqlite3.Connection) -> dict[str, Any] | None:
            cursor = connection.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?", (title, _now(), session_id)
            )
            if cursor.rowcount == 0:
                return None
            return dict(connection.execute(
                "SELECT id, title, created_at, updated_at FROM sessions WHERE id = ?", (session_id,)
            ).fetchone())

        return await self._run(rename)

    async def delete_session(self, session_id: str) -> bool:
        return await self._run(lambda connection: connection.execute(
            "DELETE FROM sessions WHERE id = ?", (session_id,)
        ).rowcount > 0)

    async def add_message(
        self, session_id: str, role: str, content: str, tool_calls: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        timestamp = _now()
        calls = tool_calls or []

        def add(connection: sqlite3.Connection) -> dict[str, Any]:
            cursor = connection.execute(
                "INSERT INTO messages (session_id, role, content, tool_calls_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, json.dumps(calls), timestamp),
            )
            connection.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (timestamp, session_id))
            if role == "user":
                connection.execute(
                    "UPDATE sessions SET title = ? WHERE id = ? AND title = ?",
                    (_title_from_question(content), session_id, DEFAULT_TITLE),
                )
            return {
                "id": cursor.lastrowid, "session_id": session_id, "role": role,
                "content": content, "tool_calls": calls, "created_at": timestamp,
            }

        return await self._run(add)

    async def list_messages(self, session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        def list_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
            if limit is None:
                rows = connection.execute(
                    "SELECT * FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
                ).fetchall()
            else:
                rows = list(reversed(connection.execute(
                    "SELECT * FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?", (session_id, limit)
                ).fetchall()))
            return [{
                "id": row["id"], "session_id": row["session_id"], "role": row["role"],
                "content": row["content"], "tool_calls": json.loads(row["tool_calls_json"]),
                "created_at": row["created_at"],
            } for row in rows]

        return await self._run(list_rows)
