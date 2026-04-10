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

# Agent model: Claude Sonnet 4.6 (strong reasoning, better throughput)
AGENT_MODEL = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-6",
    additional_request_fields={"thinking": {"type": "disabled"}},
)

# Judge model: Claude Sonnet 4.6 (strong reasoning, verified 100% on discovery baseline)
JUDGE_MODEL = "us.anthropic.claude-sonnet-4-6"

# System prompt and retry strategy
AGENT_SYSTEM_PROMPT = SYSTEM_PROMPT
AGENT_RETRY_STRATEGY = RETRY_STRATEGY

# Fake knowledge base - expanded with multiple options per cuisine for testing
FAKE_RESTAURANTS = (
    "Available restaurants:\n"
    "1. Nonna's Hearth (Italian, open daily, accepts reservations, casual atmosphere)\n"
    "2. Trattoria Roma (Italian, open Tue-Sun, accepts reservations, fine dining)\n"
    "3. Luigi's Pasta House (Italian, open daily, walk-ins welcome, casual)\n"
    "4. Bistro Parisienne (French, closed Mondays, accepts reservations, upscale)\n"
    "5. Café Laurent (French, open daily, walk-ins welcome, casual)\n"
    "6. Sakura Garden (Japanese, open daily, accepts reservations, modern)\n"
    "7. Sushi Tsunami (Japanese, open daily, walk-ins welcome, casual)\n"
    "8. The Garden Spot (Vegetarian, open daily, accepts reservations, upscale)\n"
    "9. Green Bowl Café (Vegetarian, open daily, walk-ins welcome, casual)\n"
    "10. Late Night Eats (Casual dining, open until midnight daily, walk-ins only, affordable)\n"
    "11. Luxe Prime Steakhouse (Upscale steakhouse, closed Sundays, requires reservations, premium pricing)"
)


@strands_tool
def retrieve(query: str) -> str:
    """Search the knowledge base for restaurants, menus, and availability."""
    return FAKE_RESTAURANTS


# Swap real retrieve tool (strands_tools.retrieve module) with fake one for evals
EVAL_TOOLS = [retrieve if "retrieve" in t.__name__ else t for t in TOOLS]
