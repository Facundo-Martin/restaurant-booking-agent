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

### Metrics (Strands AgentResult) — `[HIGH]` ✅ implemented

**What Strands provides natively via `AgentResult.metrics` (`EventLoopMetrics`):**
- `accumulated_usage`: `inputTokens`, `outputTokens`, `totalTokens`, `cacheReadInputTokens`, `cacheWriteInputTokens`
- `tool_metrics`: per-tool `call_count`, `error_count`, `average_latency`, `success_rate`
- `cycle_durations`: list of seconds per agent loop cycle
- `cycle_count`: total cycles for this invocation

**What was implemented:** `TokenMetricsHook` in `app/hooks.py` reads `event.result.metrics` in `AfterInvocationEvent` and emits EMF metrics to CloudWatch — `InputTokens`, `OutputTokens`, `AgentCycles`. These produce time-series data in CloudWatch Metrics for dashboards and cost alarms.

**What remains — Structured Metrics Log Entry — `[HIGH]`**

EMF metrics are aggregated (averages/sums over time). To answer per-request questions ("why did this specific session use 8 cycles?"), we need a structured log entry per invocation. This is the gap.

**Plan:** Extend `TokenMetricsHook._emit()` to also call `logger.info()` with a structured summary:

```python
def _emit(self, event: AfterInvocationEvent) -> None:
    if event.result is None:
        return
    m = event.result.metrics
    usage = m.accumulated_usage

    # EMF metrics (already in place — time-series for dashboards)
    metrics.add_metric("InputTokens", MetricUnit.Count, usage.get("inputTokens", 0))
    metrics.add_metric("OutputTokens", MetricUnit.Count, usage.get("outputTokens", 0))
    metrics.add_metric("AgentCycles", MetricUnit.Count, m.cycle_count)

    # Structured log entry — per-request detail, queryable via CW Logs Insights
    # PII-safe: only stats (counts/latencies), never tool inputs/outputs or message content
    logger.info(
        "agent_invocation_complete",
        extra={
            "input_tokens": usage.get("inputTokens", 0),
            "output_tokens": usage.get("outputTokens", 0),
            "total_tokens": usage.get("totalTokens", 0),
            "cycle_count": m.cycle_count,
            "total_duration_s": round(sum(m.cycle_durations), 3),
            "stop_reason": getattr(event.result, "stop_reason", None),
            "tool_stats": {
                name: {
                    "calls": tm.call_count,
                    "errors": tm.error_count,
                    "avg_latency_ms": round(tm.average_latency * 1000, 1),
                    "success_rate": round(tm.success_rate, 3),
                }
                for name, tm in m.tool_metrics.items()
            },
        },
    )
```

**What NOT to log:** `m.get_summary()` must not be logged wholesale — its `traces[].message` fields contain raw conversation content (assistant/user messages) that may include PII.

**CloudWatch Logs Insights queries this enables:**
```
# Requests with high cycle counts — indicates prompt/tool design issues
fields @timestamp, cycle_count, total_tokens, stop_reason
| filter message = "agent_invocation_complete" and cycle_count > 3
| sort cycle_count desc

# Tool error rates across all requests
fields @timestamp, tool_stats.retrieve.errors, tool_stats.create_booking.errors
| filter message = "agent_invocation_complete"
| stats sum(tool_stats.retrieve.errors) as retrieve_errors,
        sum(tool_stats.create_booking.errors) as booking_errors

# P95 token usage for cost forecasting
filter message = "agent_invocation_complete"
| stats percentile(total_tokens, 95) as p95_tokens,
        avg(total_tokens) as avg_tokens

# Requests stopped by guardrail
fields @timestamp, correlation_id, stop_reason
| filter message = "agent_invocation_complete" and stop_reason = "guardrail_intervened"
```

**AWS Well-Architected alignment:** The AWS Serverless observability reference confirms structured JSON logging + EMF is the recommended pattern. Log the event, emit the metric — two consumers, one source of truth.

---

### Traces — Langfuse — `[MEDIUM]`

**Decision: Langfuse Cloud.** Officially documented by Strands, LLM-specific UI (span hierarchy, token costs, latency per tool call), free tier, and naturally pairs with Ragas evals (Category 4). Data residency: Langfuse offers both EU (`cloud.langfuse.com`) and US (`us.cloud.langfuse.com`) regions.

**Why not AWS-native OTEL:**
- New ADOT layer requires `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument` — conflicts with LWA's `/opt/bootstrap`. Cannot set both.
- Old ADOT Collector sidecar avoids the conflict but has no Strands-specific documentation; ARN must be guessed.
- Strands' X-Ray section is a two-line pointer to external AWS docs — no working example exists.

**Why Langfuse over Datadog:** Langfuse is purpose-built for LLM observability — prompt management, session grouping, eval score storage. Datadog is better if the team already has a Datadog subscription for the broader stack.

**PII mitigation:**
- `OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT=512` (already set in `infra/api.ts`) truncates raw message content in span attributes
- `OTEL_TRACES_SAMPLER=traceidratio` + `OTEL_TRACES_SAMPLER_ARG=0.1` — export 10% of traces in production (reduces PII surface and cost)
- Langfuse supports data masking rules in the UI for additional scrubbing

**What to implement:**

`backend/pyproject.toml`:
```toml
"strands-agents[otel]>=0.1.0",
```

`backend/app/main.py` (module level, Lambda-only):
```python
if _in_lambda:
    from strands.telemetry import StrandsTelemetry
    StrandsTelemetry().setup_otlp_exporter()
```

`backend/app/api/routes/chat.py` — add to `Agent()`:
```python
trace_attributes={
    "session.id": request.session_id or get_correlation_id(),
    "langfuse.tags": [$app.stage],  # "production" | "staging" etc.
}
```

`infra/api.ts` — env vars for ChatFunction (store keys as SST secrets, not plaintext):
```typescript
environment: {
    // existing env vars...
    OTEL_EXPORTER_OTLP_ENDPOINT: "https://us.cloud.langfuse.com/api/public/otel",
    OTEL_EXPORTER_OTLP_HEADERS: langfuseAuthHeader.value,  // SST secret: "Authorization=Basic <base64(pk:sk)>"
    OTEL_TRACES_SAMPLER: "traceidratio",
    OTEL_TRACES_SAMPLER_ARG: $app.stage === "production" ? "0.1" : "1.0",
}
```

**What you get in Langfuse:**
- Full span tree per request: Agent → Cycle → Model invoke → Tool call
- Token usage + latency per span
- Session grouping by `session.id` — see full conversation as a timeline
- Tag filtering by stage (`production` vs `staging`)
- Eval score storage alongside traces (feeds Ragas results from Category 4)

---

### X-Ray Agent Subsegment — `[LOW]`

**What we already have:** Powertools Tracer + `@tracer.capture_method` on `get_booking_details`, `create_booking`, `delete_booking` in `tools/bookings.py` — DynamoDB calls appear as X-Ray subsegments. The Powertools logger automatically includes `xray_trace_id` in every log entry, linking logs to traces.

**What's missing:** The agent invocation itself (the 30–90s Bedrock loop) has no named subsegment in X-Ray. It appears as undifferentiated Lambda execution time.

**Optional addition:** Wrap the `agent.stream_async()` call in a Powertools Tracer subsegment:

```python
# chat.py — inside generate_chat_events()
with tracer.provider.in_subsegment("## agent.stream") as subsegment:
    subsegment.put_annotation("session_id", request.session_id or "stateless")
    async with asyncio.timeout(MAX_AGENT_SECONDS):
        async for event in agent.stream_async(user_message):
            ...
```

This adds an `agent.stream` subsegment to the X-Ray trace, making it clear how much of the Lambda duration is the Bedrock loop vs. framework overhead. No new infrastructure — Powertools Tracer is already in deps.

**Why `[LOW]` and not higher:** The structured metrics log entry already provides per-request duration. X-Ray subsegments add value for visual service map analysis, but are not critical for a single-function agent.

---

### Logs — Strands Integration — `[SKIP / Already Done]`

**Already in place:**
- Powertools Logger emits structured JSON to CloudWatch Logs with `cold_start`, `function_name`, `xray_trace_id`, correlation ID from `CorrelationIdHook`
- `_PiiRedactionFilter` on both Powertools logger and root Python logger — scrubs emails and phone numbers before CloudWatch emission
- Strands internal logs use `logging.getLogger("strands")` — a child of the root Python logger. Our root logger filter and handler already captures them. At `POWERTOOLS_LOG_LEVEL=WARNING`, only Strands warnings/errors appear in production (e.g., `bedrock threw context window overflow error`, `Found blocked output guardrail`).

**Log level for `strands` logger:** Strands' docs note `INFO` is currently unused by the SDK; `DEBUG` is very verbose (tool registration, every model call). The root logger level in production (`WARNING`) is appropriate — Strands `DEBUG`/`INFO` never fires, and `WARNING`/`ERROR` (guardrails, overflow) is surfaced.

**No changes needed here.** The structured metrics log entry from the Metrics section above is the only addition.

---

## Category 4 — Evals

> **Decision updated:** Strands Evals SDK was originally dismissed as "LLM-as-judge only". A review of the current SDK (verified against live Strands docs via MCP) showed this was outdated. The SDK now covers faithfulness, trajectory, tool selection, tool parameter accuracy, and goal success — the same surface the original plan attributed exclusively to Ragas. Decision flipped: **Strands Evals SDK (primary), Ragas `[SKIP]`**.

**Decision: Strands Evals SDK (preferred) over Ragas.**

The Strands Evals SDK now provides a full evaluation surface with no external dependencies, using Bedrock models already in the stack as judges, and integrates natively with the AWS CloudWatch / Bedrock AgentCore Observability dashboard via ADOT. Ragas requires an additional external service (Langfuse) and adds `ragas` as a dependency — complexity that is no longer justified.

**Evaluators available in `strands-evals` (current):**

| Evaluator | What it measures | Relevance to this codebase |
|---|---|---|
| `FaithfulnessEvaluator` | Are responses grounded in conversation context (KB tool results)? | Catches hallucinations about restaurants/menus |
| `TrajectoryEvaluator` | Did the agent call the right tools in the right order? | Validates `retrieve → create_booking` flow |
| `ToolSelectionAccuracyEvaluator` | Was the correct tool selected at each step? | Detects regressions in tool choice |
| `ToolParameterAccuracyEvaluator` | Are tool call parameters grounded in context, not hallucinated? | Guards against fabricated booking IDs/times |
| `GoalSuccessRateEvaluator` | Did the agent successfully achieve the user's goal? | End-to-end booking completion rate |
| `HelpfulnessEvaluator` | Is the response useful from the user's perspective? (7-level scale) | Conversation quality baseline |
| `OutputEvaluator` | Custom rubric evaluator | Domain-specific checks (e.g., no PII leakage in response) |

**What Ragas offered that Strands Evals doesn't:**
- `context_precision` — KB retrieval ranking quality. Requires exposing relevance scores from the Bedrock KB response; the `retrieve` tool doesn't surface these. Not practically applicable here.
- `answer_relevancy` — partially covered by `HelpfulnessEvaluator`.

---

### Strands Evals SDK — `[HIGH]`

**Package:** `strands-evals` (separate from main backend deps — eval-only, never deployed to Lambda).

**Test cases to build in `tests/evals/`:**

```python
from strands import Agent
from strands_evals import Case, Experiment
from strands_evals.evaluators import (
    FaithfulnessEvaluator,
    TrajectoryEvaluator,
    ToolSelectionAccuracyEvaluator,
    GoalSuccessRateEvaluator,
)
from strands_evals.extractors import tools_use_extractor
from strands_evals.mappers import StrandsInMemorySessionMapper
from strands_evals.telemetry import StrandsEvalsTelemetry
from strands_evals.types import TaskOutput

# Telemetry setup — in-memory exporter, no external service needed
telemetry = StrandsEvalsTelemetry().setup_in_memory_exporter()
memory_exporter = telemetry.in_memory_exporter

trajectory_evaluator = TrajectoryEvaluator(
    rubric="""
    For booking requests: retrieve must come before create_booking.
    For deletion requests: get_booking_details must come before delete_booking.
    Score 1.0 if order is correct, 0.0 if any step is missing or reversed.
    """
)

def run_agent(case: Case) -> TaskOutput:
    memory_exporter.clear()
    agent = Agent(
        # ...model, tools, system_prompt from agent.py...
        trace_attributes={
            "gen_ai.conversation.id": case.session_id,
            "session.id": case.session_id,
        },
        callback_handler=None,
    )
    response = agent(case.input)
    trajectory = tools_use_extractor.extract_agent_tools_used_from_messages(agent.messages)
    trajectory_evaluator.update_trajectory_description(
        tools_use_extractor.extract_tools_description(agent)
    )
    mapper = StrandsInMemorySessionMapper()
    session = mapper.map_to_session(memory_exporter.get_finished_spans(), session_id=case.session_id)
    return TaskOutput(output=str(response), trajectory=session)

test_cases = [
    Case(name="kb-lookup", input="What restaurants are open on Sunday?"),
    Case(name="booking-flow", input="Book a table for 2 at Nonna tomorrow at 7pm",
         expected_trajectory=["retrieve", "create_booking"]),
    Case(name="cancel-flow", input="Cancel booking B-123",
         expected_trajectory=["get_booking_details", "delete_booking"]),
]

experiment = Experiment(
    cases=test_cases,
    evaluators=[
        FaithfulnessEvaluator(),
        trajectory_evaluator,
        ToolSelectionAccuracyEvaluator(),
        GoalSuccessRateEvaluator(),
    ],
)
reports = experiment.run_evaluations(run_agent)
```

**CloudWatch integration:** Configure ADOT env vars (`AGENT_OBSERVABILITY_ENABLED=true`, `OTEL_METRICS_EXPORTER=awsemf`, etc.) when running evals in CI to publish scores to the **GenAI Observability: Bedrock AgentCore Observability** dashboard — no Langfuse account needed.

---

### Ragas — `[SKIP — superseded by Strands Evals SDK]`

The original plan chose Ragas for RAG-specific faithfulness metrics (`faithfulness`, `answer_relevancy`, `context_precision`) and Langfuse integration. Both rationales no longer hold:
- `FaithfulnessEvaluator` in Strands Evals covers hallucination detection grounded in KB tool results.
- `context_precision` is not practically measurable here — Bedrock KB retrieval scores are not exposed by the `retrieve` tool.
- Langfuse traces (Category 3) are not yet implemented, so there is no existing Langfuse pipeline to "pair with".

Revisit Ragas only if `context_precision` becomes measurable (requires surfacing KB retrieval scores) or if Langfuse becomes the single pane of glass for both traces and eval scores.

---

### CI Integration — `[MEDIUM]`

Add `.github/workflows/evals.yml` triggered **nightly or manually** (not on every push — Bedrock inference costs). Steps:
1. Run `uv run pytest tests/evals/ -m agent` against a deployed staging stage
2. Fail the workflow if any metric drops below threshold (e.g., faithfulness score < 0.75, trajectory pass rate < 0.9)
3. Post scores as workflow summary annotations
4. (Optional) Configure ADOT env vars to push scores to the CloudWatch AgentCore dashboard

Gate on the `agent` pytest marker already defined in `pyproject.toml`.

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
