"""Run the calculator MCP server over stdio."""

from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from mcp_server.calculator import CalculationError, CalculationResult, evaluate
from mcp_server.time_tool import TimeError, TimeResult, get_time
from mcp_server.weather import OpenMeteoWeatherProvider, WeatherError, WeatherProvider, WeatherResult

mcp = MCPServer("Calculator Demo")
weather_provider: WeatherProvider = OpenMeteoWeatherProvider()


@mcp.tool()
def calculate(
    expression: Annotated[str, Field(min_length=1, max_length=200, description="Arithmetic expression using +, -, *, /, and parentheses.")],
) -> CalculationResult:
    """Safely calculate a basic arithmetic expression."""
    try:
        return evaluate(expression)
    except CalculationError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def get_current_time(
    timezone: Annotated[str, Field(min_length=1, max_length=100, description="IANA timezone, such as Asia/Kolkata.")],
) -> TimeResult:
    """Get the current date and time in an IANA timezone."""
    try:
        return get_time(timezone)
    except TimeError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
async def get_weather(
    city: Annotated[str, Field(min_length=2, max_length=100, description="City name, optionally followed by country.")],
) -> WeatherResult:
    """Get current weather for a city from Open-Meteo."""
    try:
        return await weather_provider.get_weather(city.strip())
    except WeatherError as exc:
        raise ToolError(str(exc)) from exc


@mcp.resource("company://policies/support")
def support_policy() -> str:
    """A synthetic example of a static MCP resource."""
    return "Demo support policy: Reply within two business days. Escalate urgent incidents to the on-call team."


if __name__ == "__main__":
    mcp.run()
