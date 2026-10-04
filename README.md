# MCP Tool-Using Agent

An incremental MCP portfolio project. Milestone 1 provides one calculator server and a client that discovers its schema and invokes it over stdio. The agent and other tools come later.

## Run locally

Requires Python 3.12 or newer.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m app.client '24 * 3'
.venv/bin/python -m pytest
```

The client launches the server as a subprocess, lists the advertised tools, reads the calculator schema, and calls it. It prints the discovered schemas and structured result as JSON. An invalid expression returns an MCP tool error and exits with status 1.

To start the server independently, run `.venv/bin/python -m mcp_server.server`. It waits for MCP messages on stdin and writes protocol messages to stdout.

The calculator accepts numeric literals, parentheses, unary `+`/`-`, and `+`, `-`, `*`, `/`. It parses arithmetic with Python's AST but only evaluates those allowed nodes; it never uses `eval` or executes calls. Expression length, syntax tree size, and numeric magnitude are bounded.

The project targets the [official MCP Python SDK 2.3.0](https://pypi.org/project/mcp/). Its [server](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/servers/tools.md) and [client](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/index.md) APIs provide tool schemas and structured results.
