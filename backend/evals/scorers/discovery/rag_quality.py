"""RAG quality scorers for discovery feature."""

from autoevals import AnswerRelevancy, ContextRelevancy, Faithfulness

from braintrust import Score


async def context_relevancy_scorer(input: str, output: str, **kwargs) -> Score:
    """Score: is retrieved context relevant to the user query?"""
    context = kwargs.get("context", "")
    return ContextRelevancy()(input=input, output=output, context=context)


async def faithfulness_scorer(input: str, output: str, **kwargs) -> Score:
    """Score: does the answer stick to retrieved context (no hallucinations)?"""
    context = kwargs.get("context", "")
    return Faithfulness()(input=input, output=output, context=context)


async def answer_relevancy_scorer(input: str, output: str, **kwargs) -> Score:
    """Score: is the answer relevant to the user query?"""
    return AnswerRelevancy()(input=input, output=output)


__all__ = [
    "context_relevancy_scorer",
    "faithfulness_scorer",
    "answer_relevancy_scorer",
]
