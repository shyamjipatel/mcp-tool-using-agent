"""Reusable MCP client; the agent never imports server-side tool functions."""

import asyncio
import sys
from time import perf_counter
from typing import Any

from jsonschema import ValidationError, validate
from mcp import Client, StdioServerParameters
from mcp.types import Tool
from pydantic import BaseModel


class MCPConnectionError(RuntimeError):
    """The MCP server could not be reached or stopped responding."""


class ToolInputError(ValueError):
    """Tool arguments do not match an advertised schema."""


class ToolExecution(BaseModel):
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    is_error: bool
    duration_ms: float


def default_target(server_url: str | None = None) -> str | StdioServerParameters:
    if server_url:
        return server_url
    return StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"])


class MCPToolClient:
    def __init__(self, target: Any, timeout_seconds: float = 15.0) -> None:
        self._target = target
        self._timeout = timeout_seconds
        self._client: Client | None = None
        self._tools: dict[str, Tool] = {}

    async def __aenter__(self) -> "MCPToolClient":
        self._client = Client(self._target)
        try:
            async with asyncio.timeout(self._timeout):
                await self._client.__aenter__()
                await self.refresh_tools()
        except Exception as exc:
            if self._client is not None:
                await self._client.__aexit__(None, None, None)
            raise MCPConnectionError("Could not connect to the MCP tool server.") from exc
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._client is not None:
            await self._client.__aexit__(exc_type, exc, tb)
            self._client = None

    @property
    def tools(self) -> list[Tool]:
        return list(self._tools.values())

    async def refresh_tools(self) -> list[Tool]:
        if self._client is None:
            raise MCPConnectionError("MCP client is not connected.")
        discovered: dict[str, Tool] = {}
        cursor: str | None = None
        while True:
            page = await self._client.list_tools(cursor=cursor)
            discovered.update({tool.name: tool for tool in page.tools})
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        self._tools = discovered
        return self.tools

    async def invoke(self, name: str, arguments: dict[str, Any]) -> ToolExecution:
        if self._client is None:
            raise MCPConnectionError("MCP client is not connected.")
        tool = self._tools.get(name)
        if tool is None:
            raise ToolInputError(f"Tool is not advertised by the server: {name}")
        try:
            validate(arguments, tool.input_schema)
        except ValidationError as exc:
            raise ToolInputError(f"Invalid arguments for {name}: {exc.message}") from exc

        started = perf_counter()
        try:
            async with asyncio.timeout(self._timeout):
                response = await self._client.call_tool(name, arguments)
        except TimeoutError as exc:
            raise MCPConnectionError(f"Tool {name} timed out.") from exc
        except Exception as exc:
            raise MCPConnectionError(f"Tool {name} could not be invoked.") from exc
        error = None
        if response.is_error:
            error = next((block.text for block in response.content if block.type == "text"), "Tool failed.")
        return ToolExecution(
            name=name,
            arguments=arguments,
            result=response.structured_content if not response.is_error else None,
            error=error,
            is_error=response.is_error,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
