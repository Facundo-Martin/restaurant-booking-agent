"""Shared agent components for the restaurant booking assistant.

BedrockModel and tools are cached at module level — they are stateless and
safe to reuse across requests. The Agent itself is created per request in
chat.py to prevent conversation history from leaking between users.
"""

import os

from strands import ModelRetryStrategy
from strands.models import BedrockModel
from strands_tools import current_time, retrieve

from app.config import GUARDRAIL_ID, GUARDRAIL_VERSION, KB_ID
from app.tools.bookings import create_booking, delete_booking, get_booking_details

# The retrieve tool reads KNOWLEDGE_BASE_ID from the environment.
# Set once at module load so it's available before the first agent is created.
os.environ["KNOWLEDGE_BASE_ID"] = KB_ID

SYSTEM_PROMPT = """You are a helpful restaurant booking assistant. You help users:
- Discover restaurants and browse menus using your knowledge base
- Make, view, and cancel reservations

Always confirm booking details with the user before creating a reservation.
When a user asks about restaurants or menus, use the retrieve tool to search
the knowledge base. Use current_time when date context is needed.
"""

# boto3 retry configuration — set via environment variables so they apply to
# every boto3 client Strands creates internally (BedrockModel, retrieve tool).
# "standard" mode: exponential backoff with jitter, up to 3 total attempts.
# This handles transient Bedrock throttling (429) and service errors (5xx).
# setdefault respects values already injected by the Lambda execution environment.
#
# Note: retries multiply potential wait time — they do NOT bound it. The hard
# upper bound is asyncio.timeout(MAX_AGENT_SECONDS) in chat.py.
os.environ.setdefault("AWS_RETRY_MODE", "standard")
os.environ.setdefault("AWS_MAX_ATTEMPTS", "3")

# Strands-level retry for ModelThrottledException (rate limits).
# Default is 6 total attempts with 4s initial delay — worst case 124s, which
# exceeds the 110s asyncio.timeout in chat.py and prevents the clean SSE done event.
# Aligned with AWS_MAX_ATTEMPTS=3; worst-case wait: 2+4+20 = 26s.
RETRY_STRATEGY = ModelRetryStrategy(
    max_attempts=3,  # 1 initial + 2 retries — matches AWS_MAX_ATTEMPTS
    initial_delay=2,
    max_delay=20,  # caps exponential growth well within the 110s timeout budget
)

# Cached at module level — BedrockModel is stateless (no conversation state).
# Creating it once per cold start avoids repeated credential resolution overhead.
#
# Guardrail is attached when BEDROCK_GUARDRAIL_ID is set in the environment.
# Bedrock evaluates the guardrail before every model response, blocking prompt
# injection, PII leakage, and off-topic content at the API layer.
# Leave unset in local dev; configure via SST link once a guardrail is deployed.
model = BedrockModel(
    model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    additional_request_fields={"thinking": {"type": "disabled"}},
    **(
        {
            "guardrail_id": GUARDRAIL_ID,
            "guardrail_version": GUARDRAIL_VERSION,
            "guardrail_trace": "enabled",
        }
        if GUARDRAIL_ID
        else {}
    ),
)

# All tools available to the agent — stateless, safe to share across requests.
TOOLS = [retrieve, current_time, get_booking_details, create_booking, delete_booking]
