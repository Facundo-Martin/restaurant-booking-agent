"""POST /chat — SSE streaming via Strands agent.stream_async."""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.session import S3SessionManager

from app.agent import RETRY_STRATEGY, SYSTEM_PROMPT, TOOLS, model
from app.config import APP_STAGE, MAX_AGENT_SECONDS, SESSIONS_BUCKET
from app.hooks import CorrelationIdHook, LimitToolCallsHook, TokenMetricsHook
from app.logging import logger
from app.metrics import MetricUnit, metrics
from app.middleware import get_correlation_id
from app.models.schemas import ChatApiRequest
from app.tracer import tracer

router = APIRouter(tags=["chat"])


async def generate_chat_events(  # pylint: disable=too-many-branches,too-many-locals,too-many-statements
    request: ChatApiRequest,
) -> AsyncGenerator[ServerSentEvent, None]:
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

    # Create a conversation manager with custom window size
    conversation_manager = SlidingWindowConversationManager(
        window_size=40,  # Maximum number of messages to keep
        should_truncate_results=True,  # truncate large tool results, not messages
        per_turn=True,  # Apply management before each model cal, not just at agent loop
    )

    # S3SessionManager restores full conversation history from S3 on each Lambda invocation,
    # solving the cold-start amnesia problem. Falls back to stateless when no session_id
    # is provided (e.g., legacy clients or one-off queries).
    session_manager = (
        S3SessionManager(session_id=request.session_id, bucket=SESSIONS_BUCKET)
        if request.session_id
        else None
    )

    hooks = [
        CorrelationIdHook(),
        TokenMetricsHook(),
        LimitToolCallsHook({"retrieve": 10, "create_booking": 3, "delete_booking": 2}),
    ]

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        callback_handler=None,
        conversation_manager=conversation_manager,
        retry_strategy=RETRY_STRATEGY,
        hooks=hooks,
        session_manager=session_manager,
        trace_attributes={
            "session.id": request.session_id or get_correlation_id(),
            "langfuse.tags": [APP_STAGE],
        },
    )
    # Maps toolUseId → toolName so tool-result events can include the name.
    tool_names: dict[str, str] = {}

    try:
        with tracer.provider.in_subsegment("## agent.stream") as subsegment:
            subsegment.put_annotation("session_id", request.session_id or "stateless")
            async with asyncio.timeout(MAX_AGENT_SECONDS):
                agent_stream = agent.stream_async(user_message)
                async for event in agent_stream:
                    event: dict[
                        str, Any
                    ]  # TypedEvent (dict subclass); stream_async types as Any

                    # --- Text tokens ---
                    if "data" in event:
                        yield ServerSentEvent(
                            data=json.dumps(
                                {"type": "text-delta", "delta": event["data"]}
                            )
                        )

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
                                    yield ServerSentEvent(
                                        data=json.dumps(
                                            {
                                                "type": "tool-call-start",
                                                "toolCallId": tool_id,
                                                "toolName": tool_name,
                                                "input": tool_use.get("input") or {},
                                            }
                                        )
                                    )

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
                                        output.update(
                                            json_val
                                            if isinstance(json_val, dict)
                                            else {"result": json_val}
                                        )

                                sse_payload: dict[str, Any] = {
                                    "toolCallId": tool_id,
                                    "toolName": tool_names.get(tool_id, ""),
                                }
                                if status == "error":
                                    yield ServerSentEvent(
                                        data=json.dumps(
                                            {
                                                **sse_payload,
                                                "type": "tool-error",
                                                "error": output.get(
                                                    "text", "Tool execution failed"
                                                ),
                                            }
                                        )
                                    )
                                else:
                                    yield ServerSentEvent(
                                        data=json.dumps(
                                            {
                                                **sse_payload,
                                                "type": "tool-result",
                                                "output": output,
                                            }
                                        )
                                    )

                    # --- Agent forced to stop (token limit, guardrail, etc.) ---
                    if event.get("force_stop"):
                        reason = event.get(
                            "force_stop_reason", "Agent stopped unexpectedly"
                        )
                        logger.warning(
                            "Agent force-stopped",
                            extra={
                                "reason": reason,
                                "correlation_id": get_correlation_id(),
                            },
                        )
                        metrics.add_metric(
                            name="AgentError", unit=MetricUnit.Count, value=1
                        )
                        yield ServerSentEvent(
                            data=json.dumps({"type": "error", "error": str(reason)})
                        )

    except TimeoutError:
        logger.warning(
            "Agent stream timed out",
            extra={
                "timeout_seconds": MAX_AGENT_SECONDS,
                "correlation_id": get_correlation_id(),
            },
        )
        metrics.add_metric(name="AgentError", unit=MetricUnit.Count, value=1)
        yield ServerSentEvent(
            data=json.dumps(
                {"type": "error", "error": "Request timed out. Please try again."}
            )
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception(
            "Agent stream error", extra={"correlation_id": get_correlation_id()}
        )
        metrics.add_metric(name="AgentError", unit=MetricUnit.Count, value=1)
        yield ServerSentEvent(
            data=json.dumps({"type": "error", "error": "An unexpected error occurred."})
        )
    finally:
        # Flush EMF metrics manually — the chat Lambda runs under LWA+uvicorn so
        # @metrics.log_metrics never executes; the generator finally block is the
        # only reliable flush point for every request.
        metrics.flush_metrics()
        yield ServerSentEvent(data=json.dumps({"type": "done"}))


@router.post("/chat", operation_id="streamChat")
async def stream_chat(request: ChatApiRequest) -> EventSourceResponse:
    """Accept a chat request and return a streaming SSE response."""
    metrics.add_metric(name="ChatRequest", unit=MetricUnit.Count, value=1)
    logger.info(
        "POST /chat",
        extra={
            "message_count": len(request.messages),
            "last_message_preview": (
                request.messages[-1].content[:80] if request.messages else ""
            ),
            "correlation_id": get_correlation_id(),
        },
    )
    return EventSourceResponse(
        generate_chat_events(request),
        headers={"X-Accel-Buffering": "no"},
    )
