"""POST /chat route — invokes the Strands agent and returns its response."""

from fastapi import APIRouter

from app.agent import get_agent
from app.models.schemas import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Send a message to the restaurant booking agent and get a response.

    The agent has access to the restaurant knowledge base, current time,
    and booking management tools (create, view, delete).
    """
    agent = get_agent()
    result = agent(request.message)

    return ChatResponse(
        response=str(result),
        session_id=request.session_id,
    )
