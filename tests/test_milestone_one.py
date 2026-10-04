"""Exercise the first milestone over the real stdio transport."""

import asyncio

from app.client import run


def test_discovers_schema_and_calculates_over_stdio() -> None:
    output = asyncio.run(run("24 * 3"))
    assert output["tool"] == "calculate"
    assert output["input_schema"]["required"] == ["expression"]
    assert output["input_schema"]["properties"]["expression"]["type"] == "string"
    assert output["is_error"] is False
    assert output["result"] == {"expression": "24 * 3", "result": 72}


def test_invalid_input_is_a_controlled_tool_error() -> None:
    output = asyncio.run(run("1 / 0"))
    assert output["is_error"] is True
    assert output["result"] is None
    assert "Division by zero" in output["error"]


def test_python_execution_is_rejected() -> None:
    expression = "__import__('os').system('echo unsafe')"
    output = asyncio.run(run(expression))
    assert output["is_error"] is True
    assert "Only numbers" in output["error"]
