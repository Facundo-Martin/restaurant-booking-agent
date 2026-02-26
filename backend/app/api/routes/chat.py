"""POST /chat — SSE streaming via Strands agent callbacks."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from strands import Agent

from app.agent import SYSTEM_PROMPT, TOOLS, model
from app.models.schemas import ChatApiRequest

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


class _SSECallback:
    """Strands callback_handler that routes streaming events into an asyncio queue.

    Strands runs synchronously in a thread; this class bridges its callbacks
    into the async event loop via call_soon_threadsafe.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: "asyncio.Queue[str | None]",
    ) -> None:
        self._loop = loop
        self._q = queue
        self._seen_tool_ids: set[str] = set()

    def _put(self, event: dict) -> None:
        self._loop.call_soon_threadsafe(self._q.put_nowait, _sse(event))

    def __call__(self, **kwargs: Any) -> None:
        # Streaming text token from the LLM
        if kwargs.get("data"):
            self._put({"type": "text-delta", "delta": kwargs["data"]})

        # Tool invocation starting — emit once per unique tool call ID
        tool = kwargs.get("current_tool_use")
        if tool and tool.get("toolUseId") and tool.get("name"):
            tool_id = tool["toolUseId"]
            if tool_id not in self._seen_tool_ids:
                self._seen_tool_ids.add(tool_id)
                self._put(
                    {
                        "type": "tool-call-start",
                        "toolCallId": tool_id,
                        "toolName": tool["name"],
                        "input": tool.get("input") or {},
                    }
                )


async def _stream(request: ChatApiRequest) -> AsyncGenerator[str, None]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    cb = _SSECallback(loop, queue)
    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        callback_handler=cb,
    )

    # Use only the last user message — multi-turn memory is a future concern
    user_message = next(
        (m.content for m in reversed(request.messages) if m.role == "user"),
        "",
    )

    async def _run() -> None:
        try:
            await loop.run_in_executor(None, agent, user_message)
        except Exception as exc:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                _sse({"type": "error", "error": str(exc)}),
            )
        finally:
            # Sentinel: signals the generator to stop
            loop.call_soon_threadsafe(queue.put_nowait, None)

    asyncio.create_task(_run())

    while True:
        item = await queue.get()
        if item is None:
            break
        yield item

    yield _sse({"type": "done"})


@router.post("/chat", operation_id="streamChat")
async def chat(request: ChatApiRequest) -> StreamingResponse:
    logger.info("POST /chat — %d message(s), last: %.80r", len(request.messages), request.messages[-1].content if request.messages else "")
    return StreamingResponse(
        _stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )