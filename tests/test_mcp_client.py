"""Dynamic client discovery, invocation, validation, and failure handling."""

import asyncio

import pytest

from app.mcp.client import MCPConnectionError, MCPToolClient, ToolInputError
from mcp_server.server import mcp


def test_discover_and_invoke_in_memory() -> None:
    async def check() -> None:
        async with MCPToolClient(mcp) as client:
            tools = {tool.name: tool for tool in client.tools}
            assert set(tools) == {"calculate", "get_current_time", "get_weather"}
            assert tools["calculate"].input_schema["properties"]["expression"]["type"] == "string"
            result = await client.invoke("calculate", {"expression": "24 * 3"})
            assert result.result == {"expression": "24 * 3", "result": 72}
            assert result.is_error is False
            assert result.duration_ms >= 0

    asyncio.run(check())


def test_rejects_unadvertised_tool_and_invalid_arguments() -> None:
    async def check() -> None:
        async with MCPToolClient(mcp) as client:
            with pytest.raises(ToolInputError, match="not advertised"):
                await client.invoke("run_shell", {})
            with pytest.raises(ToolInputError, match="Invalid arguments"):
                await client.invoke("calculate", {"expression": 123})
            result = await client.invoke("calculate", {"expression": "1 / 0"})
            assert result.is_error is True
            assert "Division by zero" in result.error

    asyncio.run(check())


def test_unavailable_server_is_reported() -> None:
    async def check() -> None:
        with pytest.raises(MCPConnectionError, match="Could not connect"):
            async with MCPToolClient("http://127.0.0.1:9/mcp", timeout_seconds=1):
                pass

    asyncio.run(check())
