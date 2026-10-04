"""Offline demo still selects and invokes discovered MCP tools."""

import asyncio

from app.agent.graph import AgentService
from app.config import Settings, make_model
from mcp_server import server
from mcp_server.weather import WeatherResult


def test_demo_calculator_and_no_tool() -> None:
    model = make_model(Settings(llm_provider="demo"))
    calculator = asyncio.run(AgentService(model, server.mcp).run("What is 125 multiplied by 24?"))
    assert calculator["tool_calls"][0]["name"] == "calculate"
    assert calculator["tool_calls"][0]["result"]["result"] == 3000
    assert "3000" in calculator["answer"]
    explanation = asyncio.run(AgentService(make_model(Settings(llm_provider="demo")), server.mcp).run("What is an MCP server?"))
    assert explanation["tool_calls"] == []
    assert "protocol" in explanation["answer"]


def test_demo_weather_conversion_uses_two_tools(monkeypatch) -> None:
    class FakeWeather:
        async def get_weather(self, city: str) -> WeatherResult:
            return WeatherResult(city="Bengaluru, India", temperature_c=27, condition="Partly cloudy", observed_at="2026-10-05T12:00")

    monkeypatch.setattr(server, "weather_provider", FakeWeather())
    result = asyncio.run(AgentService(make_model(Settings(llm_provider="demo")), server.mcp).run(
        "Get the current temperature in Bangalore and convert it to Fahrenheit."
    ))
    assert [item["name"] for item in result["tool_calls"]] == ["get_weather", "calculate"]
    assert "80.6°F" in result["answer"]
