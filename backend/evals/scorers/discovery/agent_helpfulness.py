"""LLM-as-judge scorer: agent helpfulness."""

import json

import boto3

from braintrust import Score
from evals.scorers.discovery.prompts import HELPFULNESS_PROMPT


async def agent_helpfulness_scorer(input: str, output: str, **kwargs) -> Score:
    """
    Evaluate helpfulness of agent response using LLM-as-judge.

    Args:
        input: User query
        output: Agent response

    Returns:
        Score object with score 0-1 and reasoning
    """
    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

    prompt = HELPFULNESS_PROMPT.replace("{{input}}", input).replace(
        "{{output}}", output
    )

    response = bedrock.invoke_model(
        modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        body=json.dumps(
            {
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
            }
        ),
    )

    result = json.loads(response["body"].read())
    score_text = result["content"][0]["text"].strip()

    # Parse score (0-1) from model output (first line is the score)
    try:
        score = float(score_text.split("\n")[0])
    except (ValueError, IndexError):
        score = 0.5  # Default if parsing fails

    return Score(
        name="Agent Helpfulness",
        score=score,
        metadata={"reasoning": score_text},
    )


__all__ = ["agent_helpfulness_scorer"]
