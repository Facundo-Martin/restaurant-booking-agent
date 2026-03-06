# Taking Strands Agents to Production

> **Status: planning phase — reviewed against Strands SDK docs via MCP.**

Items are grouped by SDK documentation category and listed in **priority order within each category**. Irrelevant items are noted with `[SKIP]` and a rationale so they're not revisited.

Priority tags: `[IMMEDIATE]` active risk · `[HIGH]` implement soon · `[MEDIUM]` valuable later · `[LOW]` minor · `[SKIP]` not applicable

---

## Category 1 — Concepts (Foundations & Development)

### Conversation Management — `[IMMEDIATE]`

**Gap:** Agent is created per-request; client sends full message history on every call. Nothing prevents a long conversation from exceeding Claude's context window, causing an unhandled exception inside `stream_async`.

**What to implement:** Pass `SlidingWindowConversationManager` when constructing the Agent in `chat.py`:
```python
from strands.agent.conversation_manager import SlidingWindowConversationManager

agent = Agent(
    model=model,
    tools=TOOLS,
    system_prompt=SYSTEM_PROMPT,
    conversation_manager=SlidingWindowConversationManager(
        window_size=40,              # CHAT_MAX_MESSAGES=50 + headroom for tool-result messages
        should_truncate_results=True,
        per_turn=True,               # trim before each model call, not just at loop end
    ),
)
```
**Why `per_turn=True`:** The booking agent can call retrieve + 3 booking tools per turn. Without per-turn trimming, context can overflow mid-loop before `apply_management` runs at the end.

**Consider later:** `SummarizingConversationManager` — preserves older context by summarizing it rather than discarding. Costs one extra Bedrock call per summarization. Appropriate when session management (Category 1 / Session Management) lands and conversation continuity across sessions matters.

---

### Retry Strategies — `[IMMEDIATE]`

**Gap:** Two independent retry layers interact badly:
1. **boto3** layer: `AWS_RETRY_MODE=standard`, `AWS_MAX_ATTEMPTS=3` (set in `agent.py`) — handles transient HTTP errors.
2. **Strands `ModelRetryStrategy`** default: **6 total attempts**, initial delay 4s, doubling each attempt → worst-case wait **4+8+16+32+64 = 124s** before exception — **exceeds our `asyncio.timeout(110s)`**.

**Risk:** Strands retries can exhaust the Lambda timeout budget before `TimeoutError` fires, so Lambda kills the execution environment mid-stream instead of our `finally: yield done` running.

**What to implement:**
```python
from strands import Agent, ModelRetryStrategy

agent = Agent(
    model=model,
    tools=TOOLS,
    system_prompt=SYSTEM_PROMPT,
    retry_strategy=ModelRetryStrategy(
        max_attempts=3,  # matches AWS_MAX_ATTEMPTS — 1 initial + 2 retries
        initial_delay=2,
        max_delay=20,    # worst case: 2+4+20 = 26s — well within 110s budget
    ),
)
```
**Note:** `ModelRetryStrategy` handles `ModelThrottledException` only. For retrying on other exception types (e.g., `ServiceUnavailableException`), use the `AfterModelCallEvent` hook with `event.retry = True` instead (see Hooks below).

---

### Hooks — `[HIGH]`

**What Strands Hooks provide:** Strongly-typed callbacks at every point in the agent lifecycle. Key events: `BeforeInvocationEvent`, `AfterInvocationEvent`, `BeforeModelCallEvent`, `AfterModelCallEvent`, `BeforeToolCallEvent`, `AfterToolCallEvent`, `MessageAddedEvent`.

**Three concrete hooks for this codebase — implement in `app/hooks.py`:**

**Hook A: Correlation ID injection**
```python
class CorrelationIdHook(HookProvider):
    def register_hooks(self, registry):
        registry.add_callback(BeforeInvocationEvent, self.inject_correlation_id)

    def inject_correlation_id(self, event):
        logger.append_keys(correlation_id=get_correlation_id())
```
Ensures every log line inside the agent loop (model calls, tool calls) carries the request correlation ID — currently they don't.

**Hook B: Token usage → CloudWatch Metrics**
```python
class TokenMetricsHook(HookProvider):
    def register_hooks(self, registry):
        registry.add_callback(AfterInvocationEvent, self.emit_token_metrics)

    def emit_token_metrics(self, event):
        usage = event.agent.metrics.accumulated_usage
        metrics.add_metric("InputTokens", MetricUnit.Count, usage.get("inputTokens", 0))
        metrics.add_metric("OutputTokens", MetricUnit.Count, usage.get("outputTokens", 0))
        metrics.add_metric("AgentCycles", MetricUnit.Count,
                           len(event.agent.metrics.agent_invocations[0].cycles))
```
Replaces guesswork about token costs with real per-request data in CloudWatch.

**Hook C: Tool call limiter (runaway protection)**
```python
# SDK built-in pattern — use LimitToolCounts from hooks cookbook
LimitToolCounts(max_tool_counts={"create_booking": 3, "retrieve": 10, "delete_booking": 2})
```
Cancels tool calls that exceed the per-request cap, preventing pathological agent loops from running up Bedrock costs. The SDK cookbook provides the full implementation.

**Usage:**
```python
agent = Agent(
    ...,
    hooks=[CorrelationIdHook(), TokenMetricsHook(), LimitToolCounts(...)],
)
```

---

### Session Management — `[HIGH]` ✅ implemented

**Problem solved:** Each Lambda invocation previously started with no memory of prior turns. Client was sending the full `messages[]` array on every request as a workaround — payload grew linearly with conversation length and history was lost on browser refresh.

**Decision: `S3SessionManager`** — chosen over three alternatives:

| Option | Verdict | Reason |
|---|---|---|
| `FileSessionManager` | ❌ non-starter | Lambda's `/tmp` is ephemeral and not shared across instances |
| `S3SessionManager` | ✅ chosen | Serverless, pay-per-use, ~20–50ms overhead negligible vs. Bedrock latency |
| Valkey/Redis | ❌ overkill | ElastiCache minimum ~$15–50/month always-on; sub-10ms session reads don't matter at our scale |
| AgentCore Memory | ❌ wrong tool | Designed for LTM *across* sessions (semantic retrieval of past preferences), not within-session continuity |

**What was implemented:**
1. `infra/storage.ts`: `sst.aws.Bucket("AgentSessions")` + 30-day lifecycle expiry rule
2. `infra/api.ts`: `sessionsBucket` added to ChatFunction `link` (grants S3 read/write IAM automatically)
3. `config.py`: `SESSIONS_BUCKET = Resource.AgentSessions.name`
4. `schemas.py`: optional `session_id: str | None` added to `ChatApiRequest` (backward-compatible — absent = stateless fallback)
5. `chat.py`: `S3SessionManager(session_id=..., bucket=SESSIONS_BUCKET)` wired into `Agent()` when `session_id` present
6. `use-streaming-chat.ts`: UUID generated on mount, persisted to localStorage, sent on every request; only the new user message is sent in `messages[]` (full history now lives in S3)

**Interaction with `SlidingWindowConversationManager`:** S3SessionManager also persists the conversation manager state (`conversation_manager_state`), so the window position survives across Lambda invocations — both must be used together.

**Follow-up:** `AgentCoreMemorySessionManager` — cross-session LTM (user preference storage, semantic retrieval of past interactions). Evaluate when personalization becomes a requirement.

**Warning:** Cannot use a session manager on an agent that is part of a multi-agent system — only the orchestrator holds it. Not a concern for our single-agent setup.

---

### State — `[MEDIUM]`

**What it is:** Agent key-value store (`agent.state["key"] = value`) that persists across turns within a single session and is saved by `S3SessionManager`.

**Use case for this codebase:** After session management lands, use `agent.state` to store soft context like "user's preferred restaurant" or "last booking ID" so the agent doesn't re-fetch it on every turn. Currently not useful since the agent is stateless per-request.

---

### Prompts — `[MEDIUM]`

The current system prompt is functional but lacks explicit security boundaries. Covered in Category 2 / Prompt Engineering below.

---

### Hooks: Structured Output — `[SKIP]`

Not applicable. Our API returns SSE streams, not structured JSON responses from the agent. Pydantic models at the API boundary (already in place) serve the same purpose for the booking CRUD routes.

---

### Tools: Executors — `[LOW]`

**What it is:** Controls whether tool calls in a single agent loop cycle run sequentially (default) or concurrently (`ThreadPoolExecutor`).

**Relevance:** The booking agent rarely calls more than one tool per cycle. The `retrieve` + `create_booking` sequence is inherently sequential (retrieve first, then book). Not worth the added complexity at this scale.

---

### Tools: MCP — `[SKIP]`

Not applicable. All tools (`retrieve`, `current_time`, `get_booking_details`, `create_booking`, `delete_booking`) are local `@tool` functions. No MCP server is needed.

---

### Tools: Community Tools Package — `[LOW]`

Worth reviewing if we add new capabilities (e.g., email confirmation, calendar integration). Not needed for current tool set.

---

### Multi-Agent (all patterns: A2A, Agents as Tools, Swarm, Graph, Workflow) — `[SKIP]`

The restaurant booking domain is well-served by a single agent with 5 tools. Introducing a supervisor/subagent split (e.g., a "booking agent" and a "discovery agent") would add latency, cost, and orchestration complexity with no user-visible benefit. Revisit only if the tool set grows substantially.

---

### Interrupts — `[SKIP]`

Human-in-the-loop confirmation is already handled at the system prompt level ("always confirm booking details before creating a reservation"). The SDK-level `Interrupt` mechanism is designed for cases where the agent must pause and await external input mid-loop — our confirmation pattern is conversational (the agent asks in its text response; the user replies in the next turn), which doesn't require SDK interrupts.

---

## Category 2 — Safety & Security

### Guardrails — `[HIGH]` ✅ implemented

**What was implemented in `infra/ai.ts`:**

> **Pulumi correction vs. original plan:** The resource is `aws.bedrock.Guardrail` (not `aws.bedrock.AgentGuardrail`). Policy array keys use plural `s` suffix: `topicsConfigs`, `filtersConfigs`, `piiEntitiesConfigs`. Output ID is `guardrailId`, not `id`.

- Topic policy: blocks all off-topic content (only restaurant/booking allowed)
- Content policy: `HATE` + `VIOLENCE` at HIGH strength; `PROMPT_ATTACK` input-only (output filtering would block legitimate assistant responses)
- PII policy: EMAIL + PHONE anonymised; CREDIT_DEBIT_CARD_NUMBER blocked
- Word policy: AWS managed profanity list (`PROFANITY`) applied to both inputs and outputs — uses `wordPolicyConfig.managedWordListsConfigs`, not a content filter type
- Registered with `sst.Linkable.wrap(aws.bedrock.Guardrail, ...)` → `guardrailId` + `version` injected into ChatFunction at deploy time
- `config.py` reads from SST link with env var fallback for local dev
- Guardrail block sets `stop_reason="guardrail_intervened"` in Strands; existing `force_stop` handler in `chat.py` covers this path

---

### Prompt Engineering Hardening — `[MEDIUM]` ✅ implemented

Rewrote `SYSTEM_PROMPT` in `agent.py` with explicit structure:
- `PERMISSIONS` block: MAY / MAY NOT boundaries
- `BOOKING RULES`: numbered constraints including `retrieve`-first and explicit confirmation requirement
- `SECURITY` block: named injection patterns with a fixed deflection response

Defense is now layered: prompt hardening (LLM-level) + Bedrock Guardrail (API-level).

---

### PII Redaction — `[MEDIUM]` ✅ implemented

Defense is layered — three surfaces covered:

1. **Bedrock Guardrail PII policy** ✅ (implemented above) — masks EMAIL + PHONE in model I/O at the API layer before content reaches the agent.
2. **`_PiiRedactionFilter`** in `app/logging.py` ✅ — lightweight regex filter (`logging.Filter` subclass) applied to both the Powertools logger and the root Python logger (covers Strands internal logs). Scrubs emails and phone numbers from log record `msg` and `args` before CloudWatch emission. No ML models, no cold-start cost.
3. **`OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT=512`** in `infra/api.ts` ✅ — caps any single OTEL span attribute at 512 chars, preventing raw user messages from appearing verbatim in X-Ray traces.

`log_event=False` is already set (Lambda Powertools default) — do not change; enabling it would log the full API Gateway event body including all message content.

**Not used:** LLM Guard / Presidio — ML models with significant cold-start and inference overhead. Only viable in an async post-processing pipeline, not the Lambda hot path.

---

### Responsible AI — `[LOW]`

Conceptual guidance; no code changes. Review the Strands Responsible AI docs once before shipping to production as a checklist against the deployed guardrails and prompt design.

---

## Category 3 — Observability & Debugging

### Metrics (Strands AgentResult) — `[HIGH]`

**What Strands provides natively:** After each invocation, `AgentResult.metrics` (an `EventLoopMetrics` instance) contains:
- `accumulated_usage`: `inputTokens`, `outputTokens`, `totalTokens`, `cacheReadInputTokens`, `cacheWriteInputTokens`
- `tool_metrics`: per-tool call counts, success rates, avg execution time
- `cycle_durations`: list of seconds per agent loop cycle
- `agent_invocations`: per-invocation breakdown

**What we currently have:** Lambda Powertools `ChatRequest`, `AgentError`, `BookingCreated` metrics — these are event counts, not token/latency metrics.

**What to add** (via Hook B from Category 1):
- `InputTokens` / `OutputTokens` per request → cost tracking in CloudWatch
- `AgentCycles` per request → loop efficiency (high cycle count = prompt/tool design issue)
- `ToolSuccessRate` per tool (from `tool_metrics`) → detect flaky tools

These complement, not replace, the existing Powertools metrics.

---

### Traces (Strands OTEL) — `[MEDIUM]`

**What Strands provides natively:** Full OpenTelemetry traces at 4 levels — Agent span → Cycle spans → Model invoke spans → Tool execution spans. Each span carries token usage, latency, system prompt, tool inputs/outputs. Sendable to X-Ray via ADOT.

**What we currently have:** Lambda Powertools X-Ray with `@tracer.capture_method` on tool functions — gives DynamoDB call subsegments but nothing inside the Strands agent loop.

**Decision:** Complement (keep Powertools for Lambda handler, add Strands OTEL for agent internals).

**What to implement:**
```python
# pyproject.toml: add strands-agents[otel] extra
# handler_chat.py (module level — runs once per cold start):
from strands.telemetry import StrandsTelemetry
StrandsTelemetry().setup_otlp_exporter()  # routes to ADOT collector Lambda layer

# chat.py — pass correlation ID as trace attribute:
agent = Agent(
    ...,
    trace_attributes={"session.id": get_correlation_id()},
)
```

Add the ADOT Lambda layer to `ChatFunction` in `infra/api.ts` and configure `OTEL_EXPORTER_OTLP_ENDPOINT` to point to the ADOT collector.

**Result:** X-Ray shows the full agent loop — each Bedrock call, each tool call, latency per cycle — linked to the correlation ID in CloudWatch Logs.

---

### Logs — `[SKIP / Already Done]`

Lambda Powertools Logger already emits structured JSON with `cold_start`, `function_name`, `xray_trace_id`, correlation ID middleware. Strands internal logs go to the root Python logger and are captured by the same handler. No changes needed; confirm log level is `INFO` in dev and `WARNING` in production (already configured in `infra/api.ts` via `POWERTOOLS_LOG_LEVEL`).

---

## Category 4 — Strands Evals SDK

**Package:** `strands-agents-evals` (separate install). Uses LLM-as-judge with Claude 4 via Bedrock. Extends / replaces `tests/integration/test_agent.py` which is currently manual-only with no scoring.

### TrajectoryEvaluator + Tool evaluators — `[HIGH]`

Most directly tests the correctness of agent behavior for this domain.

**Test cases to build in `tests/evals/test_agent_evals.py`:**
```python
from strands_evals import Case, Experiment
from strands_evals.evaluators import TrajectoryEvaluator

cases = [
    Case(name="retrieve-before-booking",
         input="Book a table at Nonna for 2 people tomorrow",
         expected_trajectory=["retrieve", "create_booking"]),  # retrieve must come first

    Case(name="no-booking-without-confirmation",
         input="Book a table for tonight",
         expected_trajectory=["retrieve"]),  # create_booking must NOT appear without confirmation

    Case(name="booking-lookup",
         input="Show me my booking B-123",
         expected_trajectory=["get_booking_details"]),

    Case(name="delete-booking",
         input="Cancel my booking B-123 at Nonna",
         expected_trajectory=["get_booking_details", "delete_booking"]),  # verify first, then delete

    Case(name="off-topic-rejection",
         input="What is the capital of France?",
         expected_trajectory=[]),  # no tools should be called
]
```

The trajectory extractor:
```python
from strands_evals.extractors import tools_use_extractor

def get_response_with_tools(case):
    agent = Agent(model=model, tools=TOOLS, system_prompt=SYSTEM_PROMPT, callback_handler=None)
    response = agent(case.input)
    trajectory = tools_use_extractor.extract_agent_tools_used_from_messages(agent.messages)
    return {"output": str(response), "trajectory": trajectory}
```

---

### HelpfulnessEvaluator / OutputEvaluator — `[MEDIUM]`

Scores response quality and user-facing clarity. Less critical than trajectory correctness for a booking agent, but useful for prompt iteration.

**Key use case:** After prompt engineering changes (Category 2), run `HelpfulnessEvaluator` on a standard set of booking scenarios to verify the changes didn't degrade response quality.

---

### ExperimentGenerator — `[MEDIUM]`

Auto-generates test cases from tool descriptions. Run once to bootstrap a larger test suite, then version-control `experiment_files/*.json`. Prevents test suite bias from hand-written cases.

```python
from strands_evals.generators import ExperimentGenerator
# Generate from tool docstrings — one-time run, save output to file
```

---

### CI Integration — `[MEDIUM]`

Add a `.github/workflows/agent-evals.yml` workflow triggered **nightly or manually** (not on every push — judge model calls cost real Bedrock credits). Gate it on the `agent` pytest marker already defined in `pyproject.toml`. Report pass/fail rates as workflow summary annotations.

---

## Category 5 — Deployment

### Operating Agents in Production checklist — `[IMMEDIATE]`

Review against current codebase. Items already done are marked.

| Checklist item | Status |
|---|---|
| Explicit tool list (no auto-loading) | ✅ Done — `tools=[...]` explicit in `agent.py` |
| Model config explicit (temp, max_tokens, top_p) | ⚠️ Partial — model_id set; add `temperature`, `max_tokens` explicitly |
| `SlidingWindowConversationManager` | ❌ Not yet — Phase 1 |
| `ModelRetryStrategy` aligned with timeout | ❌ Not yet — Phase 1 |
| Error handling / fallback on agent error | ✅ Done — `finally: yield done` in `chat.py` |
| Streaming via `stream_async()` | ✅ Done |
| Token usage monitoring | ❌ Not yet — Phase 3 (hooks) |
| Tool execution metrics | ❌ Not yet — Phase 3 (hooks) |

**One gap to close immediately:** Add explicit `temperature` and `max_tokens` to `BedrockModel` in `agent.py`. The docs recommend explicit config for production over relying on model defaults, which can change:
```python
model = BedrockModel(
    model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    temperature=0.3,
    max_tokens=4096,
    additional_request_fields={"thinking": {"type": "disabled"}},
    ...
)
```

---

### AWS Lambda deployment — `[LOW / Already Done]`

The official Strands Lambda layer exists (`arn:aws:lambda:us-east-1:856699698935:layer:strands-agents-py3_11-aarch64:1`) but we already bundle `strands-agents` via the SST Python bundler (uv). No change needed — our packaging approach is equivalent and gives more control over versions.

**One gap noted in docs:** The Strands Lambda guide recommends **establishing a new MCP connection per invocation** (not reusing module-level connections) to prevent state leakage between users. Not relevant to us since we don't use MCP tools, but worth knowing if MCP tools are added later.

---

### Versioning & Support — `[LOW]`

- Pin `strands-agents` to a minor version in `pyproject.toml` (e.g., `>=0.1.0,<0.2.0`) to avoid surprise breaking changes from `uv lock --upgrade`.
- The X-Ray SDK enters maintenance mode February 2026 — Powertools is tracking an OTEL provider migration. Follow the Strands GitHub releases for when their OTEL provider ships (currently on the p0 roadmap).

---

## What This Codebase Already Has (Do Not Duplicate)

| What | Where | Notes |
|---|---|---|
| `asyncio.timeout(110s)` | `chat.py` | Phase 1 / Retry Strategies aligns with this |
| Lambda Powertools Logger | `app/logging.py` | JSON, cold_start, correlation IDs — keep |
| Lambda Powertools Metrics | `app/metrics.py` | `ChatRequest`, `AgentError`, `BookingCreated` — extend, don't replace |
| Lambda Powertools Tracer | `tools/bookings.py` | `@tracer.capture_method` on tool functions — keep for DynamoDB subsegments |
| `GUARDRAIL_ID` / `GUARDRAIL_VERSION` stubs | `config.py`, `agent.py` | Code path correct; just needs the resource (Category 2) |
| Pydantic input validation | `models/schemas.py` | Complementary to prompt hardening; no duplication |
| `force_stop` detection | `chat.py` | Emits error + done event; verify it handles guardrail block events too |
