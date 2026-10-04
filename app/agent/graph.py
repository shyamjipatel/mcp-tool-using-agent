"""A bounded model/tool loop driven by discovered MCP tool schemas."""

import asyncio
import json
import logging
import operator
import uuid
from typing import Annotated, Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from app.mcp.client import MCPConnectionError, MCPToolClient, ToolExecution, ToolInputError, default_target

logger = logging.getLogger(__name__)
MAX_MODEL_STEPS = 6
MAX_TOOL_CALLS = 8
SYSTEM_PROMPT = (
    "You are a concise assistant. Use the available tools for arithmetic, current time, and weather. "
    "Use tool results as facts; do not invent current data. When a tool fails, explain the limitation clearly."
)


class AgentState(MessagesState):
    steps: int
    tool_count: int
    trace: Annotated[list[ToolExecution], operator.add]


def _tool_definitions(tools: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or tool.name,
                "parameters": tool.input_schema,
            },
        }
        for tool in tools
    ]


def _message_text(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return " ".join(part.get("text", "") for part in message.content if isinstance(part, dict)).strip()


class AgentService:
    def __init__(self, model: Any, target: Any = None) -> None:
        self._model = model
        self._target = target if target is not None else default_target()

    async def run(
        self, question: str, request_id: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        request_id = request_id or str(uuid.uuid4())
        prior_messages = [
            HumanMessage(content=item["content"]) if item["role"] == "user" else AIMessage(content=item["content"])
            for item in (history or [])[-20:]
            if item["role"] in ("user", "assistant")
        ]
        async with MCPToolClient(self._target) as client:
            bound_model = self._model.bind_tools(_tool_definitions(client.tools))

            async def call_model(state: AgentState) -> dict[str, Any]:
                response = await bound_model.ainvoke([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]])
                return {"messages": [response], "steps": state["steps"] + 1}

            async def call_tools(state: AgentState) -> dict[str, Any]:
                message = state["messages"][-1]
                tool_messages: list[ToolMessage] = []
                trace: list[ToolExecution] = []
                for call in message.tool_calls:
                    name, arguments = call["name"], call["args"]
                    if state["tool_count"] + len(trace) >= MAX_TOOL_CALLS:
                        execution = ToolExecution(name=name, arguments=arguments, is_error=True, error="Tool call limit reached.", duration_ms=0)
                    else:
                        try:
                            execution = await client.invoke(name, arguments)
                        except (ToolInputError, MCPConnectionError) as exc:
                            execution = ToolExecution(name=name, arguments=arguments, is_error=True, error=str(exc), duration_ms=0)
                    trace.append(execution)
                    tool_messages.append(ToolMessage(
                        content=json.dumps({"result": execution.result, "error": execution.error}),
                        tool_call_id=call["id"],
                        name=name,
                    ))
                    logger.info(json.dumps({
                        "event": "tool_call", "request_id": request_id, "agent_step": state["steps"],
                        "tool_name": name, "tool_arguments": arguments,
                        "tool_execution_time_ms": execution.duration_ms,
                        "tool_result": execution.result, "error": execution.error,
                    }))
                return {"messages": tool_messages, "trace": trace, "tool_count": state["tool_count"] + len(trace)}

            def route(state: AgentState) -> Literal["tools", "limit", "__end__"]:
                last = state["messages"][-1]
                if not isinstance(last, AIMessage) or not last.tool_calls:
                    return END
                return "limit" if state["steps"] >= MAX_MODEL_STEPS else "tools"

            async def limit_step(state: AgentState) -> dict[str, Any]:
                return {"messages": [AIMessage(content="I reached the tool step limit and could not finish the request reliably.")]}

            graph = StateGraph(AgentState)
            graph.add_node("model", call_model)
            graph.add_node("tools", call_tools)
            graph.add_node("limit", limit_step)
            graph.add_edge(START, "model")
            graph.add_conditional_edges("model", route, {"tools": "tools", "limit": "limit", END: END})
            graph.add_edge("tools", "model")
            graph.add_edge("limit", END)

            async with asyncio.timeout(90):
                result = await graph.compile().ainvoke({
                    "messages": [*prior_messages, HumanMessage(content=question)],
                    "steps": 0, "tool_count": 0, "trace": [],
                })
        answer = _message_text(result["messages"][-1])
        logger.info(json.dumps({"event": "final_response", "request_id": request_id, "final_response": answer}))
        return {"request_id": request_id, "answer": answer, "tool_calls": [item.model_dump() for item in result["trace"]]}
