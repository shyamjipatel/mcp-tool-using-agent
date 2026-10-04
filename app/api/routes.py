"""FastAPI routes; MCP implementation stays behind the client interface."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agent.graph import AgentService
from app.config import Settings, make_model
from app.mcp.client import MCPConnectionError, MCPToolClient, ToolExecution, default_target

router = APIRouter()


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    request_id: str
    answer: str
    tool_calls: list[ToolExecution]


def get_settings() -> Settings:
    return Settings.from_env()


def get_agent(settings: Settings = Depends(get_settings)) -> AgentService:
    try:
        model = make_model(settings)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AgentService(model, default_target(settings.mcp_server_url))


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/tools")
async def list_tools(settings: Settings = Depends(get_settings)) -> list[dict[str, Any]]:
    try:
        async with MCPToolClient(default_target(settings.mcp_server_url)) as client:
            return [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "output_schema": tool.output_schema,
                }
                for tool in client.tools
            ]
    except MCPConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, agent: AgentService = Depends(get_agent)) -> ChatResponse:
    request_id = str(uuid.uuid4())
    try:
        result = await agent.run(request.question, request_id=request_id)
    except MCPConnectionError as exc:
        raise HTTPException(status_code=503, detail={"request_id": request_id, "error": str(exc)}) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail={"request_id": request_id, "error": "Agent request timed out."}) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"request_id": request_id, "error": "LLM request failed."}) from exc
    return ChatResponse.model_validate(result)
