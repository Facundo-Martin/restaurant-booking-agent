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
    import json

    import boto3

    # Load prompt template
    with open("backend/evals/scorers/discovery/prompts/proactivity.txt") as f:
        proactivity_prompt_template = f.read()

    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

    prompt = proactivity_prompt_template.replace("{{input}}", input).replace(
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

    # Parse score (0-1) from model output
    try:
        score = float(score_text.split("\n")[0])
    except (ValueError, IndexError):
        score = 0.5

    return Score(
        name="Agent Proactivity",
        score=score,
        metadata={"reasoning": score_text},
    )


__all__ = ["agent_proactivity_scorer"]
