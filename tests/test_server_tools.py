"""Contract tests for the three MCP tools and the example resource."""

import asyncio

from mcp import Client

from mcp_server import server
from mcp_server.weather import WeatherError, WeatherResult


class FakeWeather:
    async def get_weather(self, city: str) -> WeatherResult:
        if city == "Failure":
            raise WeatherError("Weather provider is unavailable.")
        return WeatherResult(city=city, temperature_c=27, condition="Partly cloudy", observed_at="2026-10-05T12:00")


def test_discovery_and_tools(monkeypatch) -> None:
    monkeypatch.setattr(server, "weather_provider", FakeWeather())

    async def check() -> None:
        async with Client(server.mcp) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert set(tools) == {"calculate", "get_current_time", "get_weather"}
            assert tools["get_weather"].input_schema["required"] == ["city"]
            assert (await client.call_tool("calculate", {"expression": "125 * 24"})).structured_content["result"] == 3000
            time_result = await client.call_tool("get_current_time", {"timezone": "Asia/Kolkata"})
            assert time_result.structured_content["timezone"] == "Asia/Kolkata"
            assert "+05:30" in time_result.structured_content["datetime"]
            weather_result = await client.call_tool("get_weather", {"city": "Bangalore"})
            assert weather_result.structured_content["temperature_c"] == 27
            resources = await client.list_resources()
            assert any(str(item.uri) == "company://policies/support" for item in resources.resources)

    asyncio.run(check())


def test_invalid_inputs_and_weather_failure(monkeypatch) -> None:
    monkeypatch.setattr(server, "weather_provider", FakeWeather())

    async def check() -> None:
        async with Client(server.mcp) as client:
            invalid_time = await client.call_tool("get_current_time", {"timezone": "Mars/Olympus"})
            assert invalid_time.is_error is True
            assert "Unknown timezone" in invalid_time.content[0].text
            invalid_city = await client.call_tool("get_weather", {"city": "x"})
            assert invalid_city.is_error is True
            failure = await client.call_tool("get_weather", {"city": "Failure"})
            assert failure.is_error is True
            assert "unavailable" in failure.content[0].text

    asyncio.run(check())
