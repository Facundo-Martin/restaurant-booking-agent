"""POST /chat — synchronous agent response."""

import logging

from fastapi import APIRouter
from strands import Agent

from app.agent import SYSTEM_PROMPT, TOOLS, model
from app.models.schemas import ChatApiRequest

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/chat", operation_id="streamChat")
async def chat(request: ChatApiRequest) -> dict[str, str]:
    user_message = next(
        (m.content for m in reversed(request.messages) if m.role == "user"),
        "",
    )
    logger.info(
        "POST /chat — %d message(s), last: %.80r",
        len(request.messages),
        request.messages[-1].content if request.messages else "",
    )
    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        callback_handler=None,
    )
    result = await agent.invoke_async(user_message)
    return {"response": str(result)}
