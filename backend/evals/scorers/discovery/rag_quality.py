"""Composite RAG quality scorer.

Returns 3 related scores: ContextRelevancy, Faithfulness, AnswerRelevancy.
"""

from autoevals import AnswerRelevancy, ContextRelevancy, Faithfulness

from braintrust import Score


async def rag_quality_scorer(input: str, output: str, **kwargs) -> list[Score]:
    """
    Composite scorer: returns 3 separate RAG quality scores.

    Bundles ContextRelevancy, Faithfulness, and AnswerRelevancy into one scorer
    to reduce overhead while keeping scores separate for debugging.

    Args:
        input: User query
        output: Agent response (final answer)
        kwargs: May include 'context' (retrieved documents)

    Returns:
        List of 3 Score objects from autoevals
    """
    context = kwargs.get("context", "")

    return [
        ContextRelevancy()(input=input, output=output, context=context),
        Faithfulness()(input=input, output=output, context=context),
        AnswerRelevancy()(input=input, output=output),
    ]


__all__ = ["rag_quality_scorer"]
