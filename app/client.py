"""Discover and call MCP tools through the SDK's stdio client."""

import argparse
import asyncio
import json
import sys
from typing import Any

from mcp import Client, StdioServerParameters
from mcp.types import Tool


async def discover_tools(client: Client) -> list[Tool]:
    tools: list[Tool] = []
    cursor: str | None = None
    while True:
        page = await client.list_tools(cursor=cursor)
        tools.extend(page.tools)
        if page.next_cursor is None:
            return tools
        cursor = page.next_cursor


async def run(expression: str) -> dict[str, Any]:
    server = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"])
    async with Client(server) as client:
        tools = await discover_tools(client)
        tool = next((item for item in tools if item.name == "calculate"), None)
        if tool is None:
            raise RuntimeError("The server did not advertise a calculate tool.")
        result = await client.call_tool(tool.name, {"expression": expression})
        return {
            "tool": tool.name,
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
            "is_error": result.is_error,
            "result": result.structured_content,
            "error": next((block.text for block in result.content if block.type == "text"), None)
            if result.is_error else None,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover and call the calculator MCP tool.")
    parser.add_argument("expression", help="Basic arithmetic expression, such as '24 * 3'")
    args = parser.parse_args()
    try:
        output = asyncio.run(run(args.expression))
    except Exception as exc:
        parser.exit(2, f"MCP connection or invocation failed: {exc}\n")
    print(json.dumps(output, indent=2))
    if output["is_error"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
