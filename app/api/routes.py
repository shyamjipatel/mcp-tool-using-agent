"""FastAPI routes; MCP implementation stays behind the client interface."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.agent.graph import AgentService
from app.config import Settings, make_model
from app.mcp.client import MCPConnectionError, MCPToolClient, ToolExecution, default_target
from app.storage.chat_store import ChatStore

router = APIRouter()


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    request_id: str
    answer: str
    tool_calls: list[ToolExecution]


class SessionCreate(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=100)


class SessionRename(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class SessionTurnResponse(BaseModel):
    session: dict[str, Any]
    user_message: dict[str, Any]
    assistant_message: dict[str, Any]
    request_id: str


def get_settings() -> Settings:
    return Settings.from_env()


def get_store(request: Request) -> ChatStore:
    return request.app.state.chat_store


def get_agent(settings: Settings = Depends(get_settings)) -> AgentService:
    try:
        model = make_model(settings)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AgentService(model, default_target(settings.mcp_server_url))


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/status")
async def app_status(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    configured = (
        settings.llm_provider == "huggingface" and bool(settings.hf_token)
        or settings.llm_provider == "openai" and bool(settings.openai_api_key)
        or settings.llm_provider == "local" and bool(settings.llm_model and settings.llm_base_url)
    )
    return {"provider": settings.llm_provider, "model": settings.llm_model or "provider default", "configured": configured}


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


@router.get("/api/sessions")
async def sessions(store: ChatStore = Depends(get_store)) -> list[dict[str, Any]]:
    return await store.list_sessions()


@router.post("/api/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(request: SessionCreate, store: ChatStore = Depends(get_store)) -> dict[str, Any]:
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Conversation title cannot be empty.")
    return await store.create_session(title)


@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str, store: ChatStore = Depends(get_store)) -> dict[str, Any]:
    session = await store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"session": session, "messages": await store.list_messages(session_id)}


@router.patch("/api/sessions/{session_id}")
async def rename_session(session_id: str, request: SessionRename, store: ChatStore = Depends(get_store)) -> dict[str, Any]:
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Conversation title cannot be empty.")
    session = await store.rename_session(session_id, title)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return session


@router.delete("/api/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, store: ChatStore = Depends(get_store)) -> None:
    if not await store.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")


@router.post("/api/sessions/{session_id}/messages", response_model=SessionTurnResponse)
async def send_message(
    session_id: str, request: ChatRequest,
    store: ChatStore = Depends(get_store), agent: AgentService = Depends(get_agent),
) -> SessionTurnResponse:
    if await store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be empty.")
    history = await store.list_messages(session_id, limit=20)
    user_message = await store.add_message(session_id, "user", question)
    request_id = str(uuid.uuid4())
    try:
        result = await agent.run(question, request_id=request_id, history=history)
    except MCPConnectionError as exc:
        raise HTTPException(status_code=503, detail={"request_id": request_id, "error": str(exc)}) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail={"request_id": request_id, "error": "Agent request timed out."}) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"request_id": request_id, "error": "LLM request failed."}) from exc
    assistant_message = await store.add_message(session_id, "assistant", result["answer"], result["tool_calls"])
    session = await store.get_session(session_id)
    return SessionTurnResponse(
        session=session, user_message=user_message, assistant_message=assistant_message, request_id=request_id,
    )
