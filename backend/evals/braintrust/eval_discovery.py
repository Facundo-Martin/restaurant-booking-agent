"""Braintrust offline eval — discovery feature (restaurant search).

Runs all discovery test cases through the agent and scores each response
with RAG quality metrics (ContextRelevancy, Faithfulness, AnswerRelevancy),
LLM-as-judge scorers (helpfulness, proactivity), and deterministic checks
(tool routing, data privacy).

Run (from repo root):
    pnpm eval:braintrust:discovery

Run (from backend/ directory):
    uv run braintrust eval --env-file .env evals/braintrust/eval_discovery.py
    # Local iteration — no upload:
    uv run braintrust eval --env-file .env --no-send-logs evals/braintrust/eval_discovery.py
"""

import os

from dotenv import load_dotenv

# Load SST resource stubs from .env before importing app modules
load_dotenv()

from braintrust import Eval  # noqa: E402
from strands import Agent  # noqa: E402
from strands import tool as strands_tool  # noqa: E402
from strands.models import BedrockModel  # noqa: E402
from strands_tools import retrieve as _real_retrieve  # noqa: E402

from app.agent.core import RETRY_STRATEGY, TOOLS  # noqa: E402
from app.agent.prompt_loader import load_system_prompt_bundle  # noqa: E402
from evals.braintrust.config import (  # noqa: E402
    BRAINTRUST_PROJECT,
    DISCOVERY_DATASET,
    DISCOVERY_SCORER_VERSION,
    EVAL_AGENT_MODEL_ID,
    EVAL_JUDGE_MODEL_ID,
)
from evals.braintrust.datasets import (  # noqa: E402
    assert_case_count_matches,
    load_dataset,
)
from evals.braintrust.manifest import EvalMetadata  # noqa: E402
from evals.braintrust.scorers.common.data_privacy import (  # noqa: E402
    data_privacy_scorer,
)
from evals.braintrust.scorers.common.tool_routing import (  # noqa: E402
    tool_routing_correctness,
)
from evals.braintrust.scorers.discovery.agent_helpfulness import (  # noqa: E402
    agent_helpfulness_scorer,
)
from evals.braintrust.scorers.discovery.agent_proactivity import (  # noqa: E402
    agent_proactivity_scorer,
)
from evals.braintrust.scorers.discovery.rag_quality import (  # noqa: E402
    answer_relevancy_scorer,
    context_relevancy_scorer,
    faithfulness_scorer,
)
from evals.discovery.cases import DISCOVERY_CASES  # noqa: E402

# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
_dataset, _rows = load_dataset(BRAINTRUST_PROJECT, DISCOVERY_DATASET, version=None)
assert_case_count_matches(_rows, DISCOVERY_CASES, DISCOVERY_DATASET)

# ---------------------------------------------------------------------------
# Agent model
# ---------------------------------------------------------------------------
_AGENT_MODEL = BedrockModel(
    model_id=EVAL_AGENT_MODEL_ID,
    temperature=0.5,
    additional_request_fields={"thinking": {"type": "disabled"}},
)

# ---------------------------------------------------------------------------
# Stub retrieve tool (returns fake restaurant list)
# ---------------------------------------------------------------------------
_FAKE_RESTAURANTS = (
    "Available restaurants: Nonna's Hearth (Italian, open daily), "
    "Bistro Parisienne (French, closed Mondays), "
    "Sakura Garden (Japanese, open daily)."
)


@strands_tool
def retrieve(query: str) -> str:  # noqa: A002
    """Search the knowledge base for restaurants."""
    return _FAKE_RESTAURANTS


_EVAL_TOOLS = [retrieve if t is _real_retrieve else t for t in TOOLS]
_PROMPT_BUNDLE = load_system_prompt_bundle()


# ---------------------------------------------------------------------------
# Task function
# ---------------------------------------------------------------------------


async def run_discovery_agent(input: str) -> str:  # noqa: A002
    """Run the discovery agent and return the response text."""
    agent = Agent(
        model=_AGENT_MODEL,
        tools=_EVAL_TOOLS,
        system_prompt=_PROMPT_BUNDLE.text,
        callback_handler=None,
        retry_strategy=RETRY_STRATEGY,
    )

    response = await agent.invoke_async(input)
    return str(response)


# ---------------------------------------------------------------------------
# Eval setup
# ---------------------------------------------------------------------------

_commit = os.environ.get("GITHUB_SHA", "local")
_experiment_name = f"discovery-{_commit[:8]}"

_metadata = EvalMetadata(
    project_name=BRAINTRUST_PROJECT,
    dataset_name=DISCOVERY_DATASET,
    prompt_slug=_PROMPT_BUNDLE.slug,
    prompt_version=_PROMPT_BUNDLE.version,
    prompt_environment=_PROMPT_BUNDLE.environment,
    agent_model_id=EVAL_AGENT_MODEL_ID,
    scorer_version=DISCOVERY_SCORER_VERSION,
    commit=_commit,
    judge_model_id=EVAL_JUDGE_MODEL_ID,
)

Eval(
    BRAINTRUST_PROJECT,
    data=_dataset,
    task=run_discovery_agent,
    scores=[
        context_relevancy_scorer,
        faithfulness_scorer,
        answer_relevancy_scorer,
        agent_helpfulness_scorer,
        agent_proactivity_scorer,
        tool_routing_correctness,
        data_privacy_scorer,
    ],
    experiment_name=_experiment_name,
    max_concurrency=1,
    metadata=_metadata.to_metadata(),
)
