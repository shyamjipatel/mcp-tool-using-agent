"""Conversation API persistence and history isolation."""

import asyncio

import httpx

from app.api.routes import get_agent, get_store
from app.main import app
from app.storage.chat_store import ChatStore


class HistoryAgent:
    def __init__(self) -> None:
        self.histories = []

    async def run(self, question: str, request_id: str, history):
        self.histories.append(history)
        return {"request_id": request_id, "answer": f"Reply to {question}", "tool_calls": []}


def test_session_crud_and_saved_context(tmp_path) -> None:
    store = ChatStore(tmp_path / "chat.db")
    agent = HistoryAgent()

    async def check() -> None:
        await store.initialize()
        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_agent] = lambda: agent
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                created = await client.post("/api/sessions", json={})
                assert created.status_code == 201
                first_id = created.json()["id"]
                second_id = (await client.post("/api/sessions", json={"title": "Second"})).json()["id"]
                assert (await client.post(f"/api/sessions/{first_id}/messages", json={"question": "Hello"})).status_code == 200
                turn = (await client.post(f"/api/sessions/{first_id}/messages", json={"question": "Continue"})).json()
                assert turn["session"]["title"] == "Hello"
                assert turn["assistant_message"]["content"] == "Reply to Continue"
                assert [item["content"] for item in agent.histories[1]] == ["Hello", "Reply to Hello"]
                assert agent.histories[0] == []
                assert len((await client.get(f"/api/sessions/{first_id}")).json()["messages"]) == 4
                assert (await client.get(f"/api/sessions/{second_id}")).json()["messages"] == []
                assert len((await client.get("/api/sessions")).json()) == 2
                renamed = await client.patch(f"/api/sessions/{first_id}", json={"title": "My chat"})
                assert renamed.json()["title"] == "My chat"
                assert (await client.delete(f"/api/sessions/{first_id}")).status_code == 204
                assert (await client.get(f"/api/sessions/{first_id}")).status_code == 404
                assert (await client.post(f"/api/sessions/{second_id}/messages", json={"question": "   "})).status_code == 422
        finally:
            app.dependency_overrides.clear()

    asyncio.run(check())
