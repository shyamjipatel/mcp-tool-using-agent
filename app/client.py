"""Discover and call MCP tools through the SDK's stdio client."""

import argparse
import asyncio
import json
import os
from typing import Any

from app.mcp.client import MCPToolClient, default_target


async def run(expression: str) -> dict[str, Any]:
    async with MCPToolClient(default_target(os.getenv("MCP_SERVER_URL"))) as client:
        tool = next((item for item in client.tools if item.name == "calculate"), None)
        if tool is None:
            raise RuntimeError("The server did not advertise a calculate tool.")
        result = await client.invoke(tool.name, {"expression": expression})
        return {
            "tool": tool.name,
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
            "is_error": result.is_error,
            "result": result.result,
            "error": result.error,
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
