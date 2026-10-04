"""The served page and persisted demo conversation work together without a token."""

import asyncio

import httpx

from app.main import app


def test_page_and_demo_chat_persist_across_requests(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "demo")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "chat.db"))

    async def check() -> None:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                page = await client.get("/")
                assert page.status_code == 200
                assert "New conversation" in page.text
                assert (await client.get("/assets/app.js")).status_code == 200
                assert (await client.get("/api/status")).json()["provider"] == "demo"
                session = (await client.post("/api/sessions", json={})).json()
                first = await client.post(
                    f"/api/sessions/{session['id']}/messages",
                    json={"question": "What is 125 multiplied by 24?"},
                )
                assert first.status_code == 200
                assert first.json()["assistant_message"]["tool_calls"][0]["name"] == "calculate"
                assert "3000" in first.json()["assistant_message"]["content"]
                second = await client.post(
                    f"/api/sessions/{session['id']}/messages", json={"question": "What is an MCP server?"},
                )
                assert second.status_code == 200
                saved = (await client.get(f"/api/sessions/{session['id']}")).json()
                assert len(saved["messages"]) == 4
                assert saved["session"]["title"] == "What is 125 multiplied by 24?"

    asyncio.run(check())
