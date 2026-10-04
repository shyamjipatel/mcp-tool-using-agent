"""Deterministic model scripts exercise the LangGraph tool loop."""

import asyncio

from langchain_core.messages import AIMessage, ToolMessage

from app.agent.graph import AgentService
from mcp_server import server
from mcp_server.weather import WeatherError, WeatherResult


class ScriptedModel:
    def __init__(self, replies: list[AIMessage]) -> None:
        self.replies = replies
        self.schemas = []
        self.seen_messages = []

    def bind_tools(self, schemas):
        self.schemas = schemas
        return self

    async def ainvoke(self, messages):
        self.seen_messages.append(messages)
        return self.replies.pop(0)


class FakeWeather:
    async def get_weather(self, city: str) -> WeatherResult:
        if city == "Failure":
            raise WeatherError("Weather provider is unavailable.")
        return WeatherResult(city=city, temperature_c=27, condition="Partly cloudy", observed_at="2026-10-05T12:00")


def call(name, args, call_id):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def test_no_tool_answer() -> None:
    model = ScriptedModel([AIMessage(content="An MCP server exposes capabilities to clients.")])
    result = asyncio.run(AgentService(model, server.mcp).run("What is an MCP server?"))
    assert result["tool_calls"] == []
    assert "exposes capabilities" in result["answer"]
    assert {schema["function"]["name"] for schema in model.schemas} == {"calculate", "get_current_time", "get_weather"}


def test_prior_session_messages_are_in_model_context() -> None:
    model = ScriptedModel([AIMessage(content="Following up on 72.")])
    history = [{"role": "user", "content": "What is 24 * 3?"}, {"role": "assistant", "content": "72"}]
    asyncio.run(AgentService(model, server.mcp).run("And double it?", history=history))
    assert [message.content for message in model.seen_messages[0][-3:]] == [
        "What is 24 * 3?", "72", "And double it?",
    ]


def test_single_tool_answer() -> None:
    model = ScriptedModel([
        call("calculate", {"expression": "125 * 24"}, "calc-1"),
        AIMessage(content="125 multiplied by 24 is 3000."),
    ])
    result = asyncio.run(AgentService(model, server.mcp).run("What is 125 times 24?"))
    assert result["tool_calls"][0]["result"]["result"] == 3000
    assert isinstance(model.seen_messages[1][-1], ToolMessage)
    assert "3000" in result["answer"]


def test_multi_step_weather_then_calculator(monkeypatch) -> None:
    monkeypatch.setattr(server, "weather_provider", FakeWeather())
    model = ScriptedModel([
        call("get_weather", {"city": "Bangalore"}, "weather-1"),
        call("calculate", {"expression": "27 * 9 / 5 + 32"}, "calc-1"),
        AIMessage(content="Bangalore is 27°C, or 80.6°F."),
    ])
    result = asyncio.run(AgentService(model, server.mcp).run("Convert Bangalore's temperature to Fahrenheit."))
    assert [item["name"] for item in result["tool_calls"]] == ["get_weather", "calculate"]
    assert result["tool_calls"][1]["result"]["result"] == 80.6
    assert "80.6" in result["answer"]


def test_invalid_arguments_and_tool_failure(monkeypatch) -> None:
    monkeypatch.setattr(server, "weather_provider", FakeWeather())
    model = ScriptedModel([
        call("calculate", {"expression": 123}, "bad-1"),
        call("get_weather", {"city": "Failure"}, "bad-2"),
        AIMessage(content="I could not get the weather or calculate that."),
    ])
    result = asyncio.run(AgentService(model, server.mcp).run("Try these tools."))
    assert all(item["is_error"] for item in result["tool_calls"])
    assert "Invalid arguments" in result["tool_calls"][0]["error"]
    assert "unavailable" in result["tool_calls"][1]["error"]
    assert "could not" in result["answer"]


def test_model_step_limit_stops_repeated_tool_calls() -> None:
    model = ScriptedModel([
        call("calculate", {"expression": "1 + 1"}, f"calc-{index}")
        for index in range(6)
    ])
    result = asyncio.run(AgentService(model, server.mcp).run("Keep calculating."))
    assert len(result["tool_calls"]) == 5
    assert "step limit" in result["answer"]
