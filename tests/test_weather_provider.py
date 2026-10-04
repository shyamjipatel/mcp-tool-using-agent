"""Mock the public provider at the HTTP boundary."""

import asyncio

import httpx
import pytest

from mcp_server.weather import OpenMeteoWeatherProvider, WeatherError


def test_bangalore_uses_india_location_and_parses_current_weather() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "geocoding-api.open-meteo.com":
            assert request.url.params["name"] == "Bengaluru, India"
            return httpx.Response(200, json={"results": [{
                "name": "Bengaluru", "country": "India", "latitude": 12.97, "longitude": 77.59,
            }]})
        assert request.url.params["current"] == "temperature_2m,weather_code"
        return httpx.Response(200, json={"current": {
            "temperature_2m": 27.1, "weather_code": 2, "time": "2026-10-05T12:00",
        }})

    provider = OpenMeteoWeatherProvider(httpx.MockTransport(respond))
    result = asyncio.run(provider.get_weather("Bangalore"))
    assert result.city == "Bengaluru, India"
    assert result.temperature_c == 27.1
    assert result.condition == "Partly cloudy"


def test_weather_provider_failure_is_controlled() -> None:
    provider = OpenMeteoWeatherProvider(httpx.MockTransport(lambda request: httpx.Response(503)))
    with pytest.raises(WeatherError, match="unavailable"):
        asyncio.run(provider.get_weather("Bangalore"))
