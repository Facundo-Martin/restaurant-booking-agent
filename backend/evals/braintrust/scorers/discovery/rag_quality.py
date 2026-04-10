"""RAG quality scorers — autoevals routed through Braintrust gateway."""

import os

import openai
from autoevals import AnswerRelevancy, ContextRelevancy, Faithfulness, init

from evals.braintrust.config import EVAL_AUTOEVALS_MODEL

# Route autoevals through Braintrust gateway using Gemini Flash (better rate limits).
# BRAINTRUST_API_KEY is already set for eval runs — no extra env vars needed.
init(
    openai.AsyncOpenAI(
        base_url="https://gateway.braintrust.dev",
        api_key=os.environ.get("BRAINTRUST_API_KEY", ""),
    )
)


async def context_relevancy_scorer(output: str, **kwargs) -> dict:
    """Wrapper: is retrieved context relevant to the user query?"""
    metadata = kwargs.get("metadata", {})
    context = metadata.get("context", "")
    input_text = kwargs.get("input", "")
    return await ContextRelevancy(model=EVAL_AUTOEVALS_MODEL).eval_async(
        input=input_text, output=output, context=context
    )


async def faithfulness_scorer(output: str, **kwargs) -> dict:
    """Wrapper: does the answer stick to retrieved context (no hallucinations)?"""
    metadata = kwargs.get("metadata", {})
    context = metadata.get("context", "")
    input_text = kwargs.get("input", "")
    return await Faithfulness(model=EVAL_AUTOEVALS_MODEL).eval_async(
        input=input_text, output=output, context=context
    )


async def answer_relevancy_scorer(output: str, **kwargs) -> dict:
    """Wrapper: is the answer relevant to the user query?"""
    metadata = kwargs.get("metadata", {})
    context = metadata.get("context", "")
    input_text = kwargs.get("input", "")
    return await AnswerRelevancy(model=EVAL_AUTOEVALS_MODEL).eval_async(
        input=input_text, output=output, context=context
    )


__all__ = [
    "context_relevancy_scorer",
    "faithfulness_scorer",
    "answer_relevancy_scorer",
]
