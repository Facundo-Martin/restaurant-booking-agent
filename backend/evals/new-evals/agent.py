"""Shared agent configuration for all evals.

Contains:
- Agent model (Bedrock Claude Haiku)
- Judge model (Llama 3 8B for cost + rate limiting)
- Fake tools (retrieve stub returning static restaurant data)
- Fake data (restaurant list for consistent evaluations)
- System prompt and retry strategy from app.agent.core
"""

from strands import tool as strands_tool
from strands.models import BedrockModel

from app.agent.core import RETRY_STRATEGY, SYSTEM_PROMPT, TOOLS

# Agent model: Haiku for speed + cost
AGENT_MODEL = BedrockModel(
    model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
    additional_request_fields={"thinking": {"type": "disabled"}},
)

# Judge model: Claude Haiku (same as agent model for consistency and cost)
JUDGE_MODEL = "us.anthropic.claude-3-5-haiku-20241022-v1:0"

# System prompt and retry strategy
AGENT_SYSTEM_PROMPT = SYSTEM_PROMPT
AGENT_RETRY_STRATEGY = RETRY_STRATEGY

# Fake data
FAKE_RESTAURANTS = (
    "Available restaurants: Nonna's Hearth (Italian, open daily, accepts reservations), "
    "Bistro Parisienne (French, closed Mondays, accepts reservations), "
    "Sakura Garden (Japanese, open daily, accepts reservations)."
)


@strands_tool
def retrieve(query: str) -> str:
    """Search the knowledge base for restaurants, menus, and availability."""
    return FAKE_RESTAURANTS


# Swap real retrieve tool (strands_tools.retrieve module) with fake one for evals
EVAL_TOOLS = [retrieve if "retrieve" in t.__name__ else t for t in TOOLS]
