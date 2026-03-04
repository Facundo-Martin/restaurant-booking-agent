"""POST /chat — SSE streaming via Strands agent.stream_async."""

import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from strands import Agent

from app.agent import SYSTEM_PROMPT, TOOLS, model
from app.logging import logger
from app.middleware import get_correlation_id
from app.models.schemas import ChatApiRequest
router = APIRouter(tags=["chat"])


async def generate_chat_events(request: ChatApiRequest) -> AsyncGenerator[ServerSentEvent, None]:
    """Yield SSE events from a Strands agent stream for a single chat request.

    The Agent is created per request to isolate conversation state between
    users. The expensive singletons (BedrockModel, tools) live in agent.py
    and are reused across requests.

    Event mapping (Strands → frontend SSE protocol):
      event["data"]                   → text-delta
      event["message"] role=assistant → tool-call-start  (complete input; fires before tool runs)
      event["message"] role=user      → tool-result / tool-error  (fires after tool runs)
      event["force_stop"]             → error  (token limit, guardrail, etc.)
      exception                       → error
      finally                         → done
    """
    user_message = next(
        (m.content for m in reversed(request.messages) if m.role == "user"),
        "",
    )
    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        callback_handler=None,
    )
    # Maps toolUseId → toolName so tool-result events can include the name.
    tool_names: dict[str, str] = {}

    try:
        agent_stream = agent.stream_async(user_message)
        async for event in agent_stream:
            event: dict[str, Any]  # TypedEvent (dict subclass); stream_async types as Any

            # --- Text tokens ---
            if "data" in event:
                yield ServerSentEvent(data=json.dumps({"type": "text-delta", "delta": event["data"]}))

            # --- Tool lifecycle ---
            # Strands emits a "message" event twice per tool cycle:
            #   role=assistant  after the model finishes generating (full tool input available)
            #   role=user       after the tool executes (contains the tool result)
            message = event.get("message")
            if message:
                role = message.get("role")
                content = message.get("content", [])

                if role == "assistant":
                    for block in content:
                        tool_use = block.get("toolUse")
                        if tool_use:
                            tool_id = tool_use["toolUseId"]
                            tool_name = tool_use["name"]
                            tool_names[tool_id] = tool_name
                            yield ServerSentEvent(data=json.dumps({
                                "type": "tool-call-start",
                                "toolCallId": tool_id,
                                "toolName": tool_name,
                                "input": tool_use.get("input") or {},
                            }))

                elif role == "user":
                    for block in content:
                        tool_result = block.get("toolResult")
                        if not tool_result:
                            continue
                        tool_id = tool_result["toolUseId"]
                        status = tool_result.get("status", "success")

                        # Flatten ToolResultContent blocks into a single output dict.
                        # Each block can carry text, json, image, or document — we surface text/json.
                        output: dict[str, Any] = {}
                        for result_content in tool_result.get("content", []):
                            if "text" in result_content:
                                output["text"] = result_content["text"]
                            if "json" in result_content:
                                json_val = result_content["json"]
                                output.update(json_val if isinstance(json_val, dict) else {"result": json_val})

                        sse_payload: dict[str, Any] = {
                            "toolCallId": tool_id,
                            "toolName": tool_names.get(tool_id, ""),
                        }
                        if status == "error":
                            yield ServerSentEvent(data=json.dumps({
                                **sse_payload,
                                "type": "tool-error",
                                "error": output.get("text", "Tool execution failed"),
                            }))
                        else:
                            yield ServerSentEvent(data=json.dumps({
                                **sse_payload,
                                "type": "tool-result",
                                "output": output,
                            }))

            # --- Agent forced to stop (token limit, guardrail, etc.) ---
            if event.get("force_stop"):
                reason = event.get("force_stop_reason", "Agent stopped unexpectedly")
                logger.warning("Agent force-stopped", extra={"reason": reason, "correlation_id": get_correlation_id()})
                yield ServerSentEvent(data=json.dumps({"type": "error", "error": str(reason)}))

    except Exception:
        logger.exception("Agent stream error", extra={"correlation_id": get_correlation_id()})
        yield ServerSentEvent(data=json.dumps({"type": "error", "error": "An unexpected error occurred."}))
    finally:
        yield ServerSentEvent(data=json.dumps({"type": "done"}))


@router.post("/chat", operation_id="streamChat")
async def stream_chat(request: ChatApiRequest) -> EventSourceResponse:
    logger.info(
        "POST /chat",
        extra={
            "message_count": len(request.messages),
            "last_message_preview": (request.messages[-1].content[:80] if request.messages else ""),
            "correlation_id": get_correlation_id(),
        },
    )
    return EventSourceResponse(
        generate_chat_events(request),
        headers={"X-Accel-Buffering": "no"},
    )
