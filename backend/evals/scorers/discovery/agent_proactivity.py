"""LLM-as-judge scorer: agent proactivity."""

from braintrust import Score


async def agent_proactivity_scorer(input: str, output: str, **kwargs) -> Score:
    """
    Evaluate proactivity of agent response using LLM-as-judge.

    Args:
        input: User query
        output: Agent response

    Returns:
        Score object with score 0-1 and reasoning
    """
    # Implementation in Phase 3
    pass


__all__ = ["agent_proactivity_scorer"]
