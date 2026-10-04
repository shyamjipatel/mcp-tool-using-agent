"""Replaceable weather provider with an Open-Meteo implementation."""

from typing import Protocol

import httpx
from pydantic import BaseModel, Field


class WeatherError(ValueError):
    """Weather could not be retrieved for the requested city."""


class WeatherResult(BaseModel):
    city: str
    temperature_c: float = Field(description="Current air temperature in Celsius.")
    condition: str
    observed_at: str
    source: str = "Open-Meteo"


class WeatherProvider(Protocol):
    async def get_weather(self, city: str) -> WeatherResult: ...


def describe_weather(code: int) -> str:
    if code == 0:
        return "Clear sky"
    if code in (1, 2):
        return "Partly cloudy"
    if code == 3:
        return "Overcast"
    if code in (45, 48):
        return "Fog"
    if code in (51, 53, 55, 56, 57):
        return "Drizzle"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "Rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "Snow"
    if code in (95, 96, 99):
        return "Thunderstorm"
    return "Unknown"


class OpenMeteoWeatherProvider:
    async def get_weather(self, city: str) -> WeatherResult:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                location_response = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": city, "count": 1, "language": "en", "format": "json"},
                )
                location_response.raise_for_status()
                locations = location_response.json().get("results") or []
                if not locations:
                    raise WeatherError(f"City not found: {city}")
                location = locations[0]
                forecast_response = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": location["latitude"],
                        "longitude": location["longitude"],
                        "current": "temperature_2m,weather_code",
                        "timezone": "auto",
                    },
                )
                forecast_response.raise_for_status()
                current = forecast_response.json()["current"]
                return WeatherResult(
                    city=f"{location['name']}, {location.get('country', '')}".rstrip(", "),
                    temperature_c=current["temperature_2m"],
                    condition=describe_weather(current["weather_code"]),
                    observed_at=current["time"],
                )
        except WeatherError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise WeatherError("Weather provider is unavailable or returned invalid data.") from exc
