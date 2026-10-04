"""Deterministic, clearly labeled model substitute for offline portfolio demos."""

import json
import re
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


class DemoModel:
    def __init__(self) -> None:
        self._available: set[str] = set()

    def bind_tools(self, tools: list[dict[str, Any]]) -> "DemoModel":
        self._available = {tool["function"]["name"] for tool in tools}
        return self

    def _call(self, name: str, arguments: dict[str, Any]) -> AIMessage:
        if name not in self._available:
            return AIMessage(content=f"The {name} tool is unavailable in this demo.")
        return AIMessage(content="", tool_calls=[{
            "name": name, "args": arguments, "id": f"demo-{uuid.uuid4().hex[:12]}",
        }])

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        question = next(
            (message.content for message in reversed(messages) if isinstance(message, HumanMessage)), ""
        )
        lower = question.lower()
        latest = messages[-1]
        if isinstance(latest, ToolMessage):
            payload = json.loads(latest.content)
            if payload.get("error"):
                return AIMessage(content=f"The tool could not complete that request: {payload['error']}")
            result = payload.get("result") or {}
            if "temperature_c" in result:
                if "fahrenheit" in lower or "°f" in lower:
                    return self._call("calculate", {"expression": f"{result['temperature_c']} * 9 / 5 + 32"})
                return AIMessage(content=f"It is {result['temperature_c']}°C and {result['condition'].lower()} in {result['city']} (Open-Meteo).")
            if "timezone" in result:
                return AIMessage(content=f"The current time in {result['timezone']} is {result['formatted']}.")
            if "expression" in result:
                if "fahrenheit" in lower or "°f" in lower:
                    weather = next((
                        json.loads(message.content).get("result", {})
                        for message in reversed(messages[:-1])
                        if isinstance(message, ToolMessage) and "temperature_c" in message.content
                    ), {})
                    return AIMessage(content=f"{weather.get('city', 'The location')} is {weather.get('temperature_c', '?')}°C, or {result['result']}°F.")
                return AIMessage(content=f"The result is {result['result']}.")

        if any(word in lower for word in ("weather", "temperature", "forecast")):
            match = re.search(r"\b(?:in|for)\s+([a-zA-Z][a-zA-Z ,]{1,48}?)(?:\s+and\b|\s+to\b|[?.!]|$)", question, re.I)
            city = match.group(1).strip() if match else "Bangalore"
            return self._call("get_weather", {"city": city})
        if "time" in lower and any(word in lower for word in ("current", "now", "what time")):
            zone = re.search(r"\b[A-Za-z_]+/[A-Za-z_]+\b", question)
            timezone = zone.group(0) if zone else "Asia/Kolkata" if "india" in lower else "UTC"
            return self._call("get_current_time", {"timezone": timezone})
        expression = self._arithmetic(question)
        if expression:
            return self._call("calculate", {"expression": expression})
        if "mcp" in lower:
            return AIMessage(content="An MCP server exposes tools, resources, and prompts through a standard protocol so an AI host can discover and use them.")
        return AIMessage(content="This offline demo understands arithmetic, current time, and weather examples. Configure Hugging Face or OpenAI for open-ended questions.")

    @staticmethod
    def _arithmetic(question: str) -> str | None:
        number = r"(-?\d+(?:\.\d+)?)"
        operations = (
            (r"multiplied by|times", "*"),
            (r"divided by", "/"),
            (r"plus|added to", "+"),
            (r"minus|subtract", "-"),
        )
        for phrase, symbol in operations:
            match = re.search(rf"{number}\s+(?:{phrase})\s+{number}", question, re.I)
            if match:
                return f"{match.group(1)} {symbol} {match.group(2)}"
        match = re.search(rf"{number}\s*([+*/-])\s*{number}", question)
        if match:
            return f"{match.group(1)} {match.group(2)} {match.group(3)}"
        return None
