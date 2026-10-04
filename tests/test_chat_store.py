"""Persistence contract for sessions and messages."""

import asyncio

from app.storage.chat_store import ChatStore


def test_sessions_messages_survive_store_recreation(tmp_path) -> None:
    path = tmp_path / "chat.db"

    async def check() -> None:
        store = ChatStore(path)
        await store.initialize()
        first = await store.create_session()
        second = await store.create_session("Research")
        await store.add_message(first["id"], "user", "What is 24 * 3?")
        await store.add_message(first["id"], "assistant", "72", [{"name": "calculate", "result": {"result": 72}}])
        await store.add_message(second["id"], "user", "What is MCP?")

        reopened = ChatStore(path)
        await reopened.initialize()
        sessions = await reopened.list_sessions()
        assert len(sessions) == 2
        assert any(item["title"] == "What is 24 * 3?" and item["message_count"] == 2 for item in sessions)
        messages = await reopened.list_messages(first["id"])
        assert [item["role"] for item in messages] == ["user", "assistant"]
        assert messages[1]["tool_calls"][0]["result"]["result"] == 72
        assert (await reopened.list_messages(first["id"], limit=1))[0]["content"] == "72"
        assert (await reopened.rename_session(first["id"], "Arithmetic"))["title"] == "Arithmetic"
        assert await reopened.delete_session(first["id"]) is True
        assert await reopened.list_messages(first["id"]) == []
        assert await reopened.delete_session(first["id"]) is False

    asyncio.run(check())
