"""Composite RAG quality scorer.

Returns 3 related scores: ContextRelevancy, Faithfulness, AnswerRelevancy.
"""

from braintrust import Score


async def rag_quality_scorer(input: str, output: str, **kwargs) -> list[Score]:
    """
    Composite scorer: returns 3 separate RAG quality scores.

    Args:
        input: User query
        output: Agent response
        kwargs: May include 'context' (retrieved documents)

    Returns:
        List of 3 Score objects
    """
    # Implementation in Phase 3
    pass


__all__ = ["rag_quality_scorer"]
