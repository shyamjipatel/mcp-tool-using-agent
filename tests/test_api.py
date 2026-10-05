"""HTTP tests without external LLM or weather calls."""

import asyncio

import httpx

from app.api.routes import get_agent, get_settings
from app.config import Settings
from app.main import app


class FakeAgent:
    async def run(self, question: str, request_id: str):
        return {"request_id": request_id, "answer": f"Answered: {question}", "tool_calls": []}


def test_health_tools_and_chat() -> None:
    app.dependency_overrides[get_agent] = lambda: FakeAgent()
    app.dependency_overrides[get_settings] = lambda: Settings()

    async def check() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            page = await client.get("/")
            assert page.status_code == 200
            assert "ToolMesh — MCP Agent Workspace" in page.text
            assert (await client.get("/assets/styles.css")).status_code == 200
            assert (await client.get("/assets/app.js")).status_code == 200
            assert (await client.get("/health")).json() == {"status": "ok"}
            tools = (await client.get("/tools")).json()
            assert {tool["name"] for tool in tools} == {"calculate", "get_current_time", "get_weather"}
            response = await client.post("/chat", json={"question": "Hello"})
            assert response.status_code == 200
            assert response.json()["answer"] == "Answered: Hello"
            assert response.json()["request_id"]
            assert (await client.post("/chat", json={"question": ""})).status_code == 422

    try:
        asyncio.run(check())
    finally:
        app.dependency_overrides.clear()


def test_missing_provider_token_returns_service_error() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings()

    async def check() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/chat", json={"question": "Hello"})
            assert response.status_code == 503
            assert "HF_TOKEN" in response.json()["detail"]

    try:
        asyncio.run(check())
    finally:
        app.dependency_overrides.clear()
