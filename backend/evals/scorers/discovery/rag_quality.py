"""RAG quality scorers — autoevals adapters for Braintrust signature."""

from autoevals import AnswerRelevancy, ContextRelevancy, Faithfulness


def context_relevancy_scorer(output: str, **kwargs) -> dict:
    """Wrapper: is retrieved context relevant to the user query?"""
    context = kwargs.get("context", "")
    input_text = kwargs.get("input", "")
    return ContextRelevancy()(input=input_text, output=output, context=context)


def faithfulness_scorer(output: str, **kwargs) -> dict:
    """Wrapper: does the answer stick to retrieved context (no hallucinations)?"""
    context = kwargs.get("context", "")
    input_text = kwargs.get("input", "")
    return Faithfulness()(input=input_text, output=output, context=context)


def answer_relevancy_scorer(output: str, **kwargs) -> dict:
    """Wrapper: is the answer relevant to the user query?"""
    input_text = kwargs.get("input", "")
    return AnswerRelevancy()(input=input_text, output=output)


__all__ = [
    "context_relevancy_scorer",
    "faithfulness_scorer",
    "answer_relevancy_scorer",
]
