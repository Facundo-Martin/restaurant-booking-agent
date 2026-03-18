# Taking Strands Agents to Production

> **Status: complete — all items implemented. Branch `facundomartin98/fac-165-take-strands-agents-into-production`.**

Items are grouped by SDK documentation category and listed in **priority order within each category**. Irrelevant items are noted with `[SKIP]` and a rationale so they're not revisited.

Priority tags: `[IMMEDIATE]` active risk · `[HIGH]` implement soon · `[MEDIUM]` valuable later · `[LOW]` minor · `[SKIP]` not applicable

---

## Category 1 — Concepts (Foundations & Development)

### Conversation Management — `[IMMEDIATE]` ✅ implemented

**What was implemented:** `SlidingWindowConversationManager` wired into `Agent()` in `chat.py`:
```python
conversation_manager = SlidingWindowConversationManager(
    window_size=40,              # headroom above CHAT_MAX_MESSAGES=50
    should_truncate_results=True,
    per_turn=True,               # trim before each model call, not just at loop end
)
```
**Why `per_turn=True`:** The booking agent can call retrieve + 3 booking tools per turn. Without per-turn trimming, context can overflow mid-loop before `apply_management` runs.

**`S3SessionManager` persists conversation manager state** across Lambda invocations, so the sliding window position survives cold starts. Both must be used together.

**Consider later:** `SummarizingConversationManager` — preserves older context by summarizing rather than discarding. Appropriate if session continuity across many long conversations becomes a requirement.

---

### Retry Strategies — `[IMMEDIATE]` ✅ implemented

**What was implemented:** `RETRY_STRATEGY` module-level singleton in `backend/app/agent/core.py`:
```python
RETRY_STRATEGY = ModelRetryStrategy(
    max_attempts=3,   # 1 initial + 2 retries — matches AWS_MAX_ATTEMPTS
    initial_delay=2,
    max_delay=20,     # worst case: 2+4+20 = 26s — well within 110s asyncio.timeout
)
```
Also set via env vars at module load (apply to every internal boto3 client Strands creates):
```python
os.environ.setdefault("AWS_RETRY_MODE", "standard")
os.environ.setdefault("AWS_MAX_ATTEMPTS", "3")
```
**Why:** Strands' default is 6 attempts × exponential backoff → worst-case 124s, exceeding `asyncio.timeout(110s)` and killing the Lambda mid-stream before `finally: yield done` fires.

**Note:** `ModelRetryStrategy` handles `ModelThrottledException` only. Transient HTTP errors are handled by the boto3 standard retry layer above.

---

### Hooks — `[HIGH]` ✅ implemented

**What was implemented:** Three hooks in `backend/app/agent/hooks.py`, wired into `Agent()` in `chat.py`:

**Hook A: `CorrelationIdHook`** — injects the request correlation ID into the Powertools logger at `BeforeInvocationEvent` so every log line inside the Strands event loop (model calls, tool calls) carries it.

**Hook B: `TokenMetricsHook`** — at `AfterInvocationEvent` reads `event.result.metrics.accumulated_usage` and:
- emits EMF metrics (`InputTokens`, `OutputTokens`, `AgentCycles`) to CloudWatch
- logs `agent_invocation_complete` structured entry with full per-tool stats (calls, errors, avg_latency_ms, success_rate) — queryable via CloudWatch Logs Insights

**Hook C: `LimitToolCallsHook`** — custom implementation (not from SDK cookbook; SDK cookbook version did not exist at the time). Tracks per-tool call counts at `BeforeToolCallEvent` and sets `event.cancel_tool` when the limit is exceeded. Limits: `retrieve=10`, `create_booking=3`, `delete_booking=2`. Uses a `threading.Lock` because tool callbacks may run concurrently with a thread executor.

**Note:** `AgentResult.metrics` API changed between doc authoring and implementation — `event.result.metrics` (not `event.agent.metrics`) is the correct path in `AfterInvocationEvent`.

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

**What was implemented:** `TokenMetricsHook` in `app/agent/hooks.py` reads `event.result.metrics` in `AfterInvocationEvent` and:
- emits EMF metrics (`InputTokens`, `OutputTokens`, `AgentCycles`) to CloudWatch
- logs `agent_invocation_complete` structured entry per request

**Structured Metrics Log Entry — ✅ also implemented** (previously listed as remaining gap):

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

### Traces — Langfuse — `[MEDIUM]` ✅ implemented

**Decision: Langfuse Cloud** over AWS-native OTEL. ADOT's new layer requires `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument` which conflicts with LWA's `/opt/bootstrap`; Langfuse is officially documented by Strands with a working integration.

**What was implemented:**

`backend/pyproject.toml`: `strands-agents[otel]` extra

`backend/app/main.py` — Lambda-only, guarded on the OTLP endpoint being set (silent no-op in local dev and stages without the secret configured):
```python
if _in_lambda and os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
    from strands.telemetry import StrandsTelemetry
    StrandsTelemetry().setup_otlp_exporter()
```

`chat.py` — `trace_attributes` wired into `Agent()`:
```python
trace_attributes={
    "session.id": request.session_id or get_correlation_id(),
    "langfuse.tags": [APP_STAGE],
}
```

`infra/api.ts` — env vars for ChatFunction (keys stored as SST secrets):
```typescript
OTEL_EXPORTER_OTLP_ENDPOINT: "https://us.cloud.langfuse.com/api/public/otel",
OTEL_EXPORTER_OTLP_HEADERS: langfuseAuthHeader.value,
OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT: "512",   // PII truncation
OTEL_TRACES_SAMPLER: "traceidratio",
OTEL_TRACES_SAMPLER_ARG: $app.stage === "production" ? "0.1" : "1.0",
```

**What you get:** Full span tree (Agent → Cycle → Model → Tool), token usage + latency per span, session grouping by `session.id`, stage tag filtering.

---

### X-Ray Agent Subsegment — `[LOW]` ✅ implemented

**What was added:** `agent.stream_async()` is now wrapped in a named Powertools Tracer subsegment inside `generate_chat_events()`:
```python
with tracer.provider.in_subsegment("## agent.stream") as subsegment:
    subsegment.put_annotation("session_id", request.session_id or "stateless")
    async with asyncio.timeout(MAX_AGENT_SECONDS):
        async for event in agent.stream_async(user_message):
            ...
```
This makes the 30–90s Bedrock loop a named segment in X-Ray, distinguishing it from framework overhead. No new infrastructure — Powertools Tracer was already in deps.

**Existing X-Ray coverage:** `@tracer.capture_method` on `get_booking_details`, `create_booking`, `delete_booking` in `tools/bookings.py` — DynamoDB calls are already X-Ray subsegments. Powertools logger includes `xray_trace_id` in every log line, linking logs to traces.

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

### Strands Evals SDK — `[HIGH]` ✅ implemented

**What was implemented:** Three eval files in `backend/tests/evals/`:

- **`test_agent_evals.py`** — pytest-based suite (marked `@pytest.mark.agent`). Uses `FaithfulnessEvaluator` + `TrajectoryEvaluator` with Claude Haiku as judge. Runs via `pytest tests/evals/ -m agent`.
- **`basic_eval.py`** — standalone script: faithfulness + goal success cases. Haiku as both agent and judge. Saves per-case scores/reasons as JSON to `tests/evals/experiment_files/` with timestamps.
- **`trajectory_eval.py`** — standalone script: validates `retrieve → create_booking` and `get_booking_details → delete_booking` order. Uses deterministic mocked tool responses (canned `_FAKE_RESTAURANTS`, `_FAKE_BOOKING`) so trajectory scoring is repeatable without live KB calls. The `retrieve` tool is replaced by a `@strands_tool`-decorated stub (not `patch()`, which doesn't work once TOOLS already holds a reference to the real function).

**Key implementation decisions:**
- Agent model for evals: **Haiku** (`us.anthropic.claude-3-5-haiku-20241022-v1:0`) — faster, cheaper, higher rate limits, sufficient for following booking rules
- Judge model: **Haiku** — same reasoning, no meaningful accuracy loss for rubric scoring
- `StrandsInMemorySessionMapper` / `StrandsEvalsTelemetry.setup_in_memory_exporter()` — no external service needed

**Note:** `StrandsInMemorySessionMapper` was referenced in original plan but the actual SDK trajectory extraction uses `tools_use_extractor.extract_agent_tools_used_from_messages(agent.messages)` directly — no in-memory telemetry span mapping needed for trajectory eval.

---

### Ragas — `[SKIP — superseded by Strands Evals SDK]`

The original plan chose Ragas for RAG-specific faithfulness metrics (`faithfulness`, `answer_relevancy`, `context_precision`) and Langfuse integration. Both rationales no longer hold:
- `FaithfulnessEvaluator` in Strands Evals covers hallucination detection grounded in KB tool results.
- `context_precision` is not practically measurable here — Bedrock KB retrieval scores are not exposed by the `retrieve` tool.
- Langfuse traces (Category 3) are not yet implemented, so there is no existing Langfuse pipeline to "pair with".

Revisit Ragas only if `context_precision` becomes measurable (requires surfacing KB retrieval scores) or if Langfuse becomes the single pane of glass for both traces and eval scores. Langfuse is now implemented (Category 3) but the pipeline integration is not yet set up.

---

### CI Integration — `[MEDIUM]` ✅ implemented

**What was implemented:** `.github/workflows/evals.yml` — nightly at 02:00 UTC + `workflow_dispatch` with stage input.

Key details:
- Runs `uv run pytest tests/evals/ -m agent -v` against a staging deployment
- Injects minimal SST resource stubs via env vars so `config.py` imports without a live stack
- Posts eval output as GitHub Actions step summary
- `concurrency: group: evals-${{ github.ref }}` — cancels concurrent runs to protect shared Bedrock throttle budget
- Only runs on `main` for scheduled triggers; `workflow_dispatch` can run on any branch

---

## Category 5 — Deployment

### Operating Agents in Production checklist — `[IMMEDIATE]` ✅ complete

| Checklist item | Status |
|---|---|
| Explicit tool list (no auto-loading) | ✅ Done — `tools=[...]` explicit in `agent/core.py` |
| Model config explicit (model_id, thinking disabled, temperature, max_tokens, top_p) | ✅ Done — `temperature=0.3`, `max_tokens=4096`, `top_p=0.9` set in `agent/core.py` |
| `SlidingWindowConversationManager` | ✅ Done — `chat.py`, `window_size=40, per_turn=True` |
| `ModelRetryStrategy` aligned with timeout | ✅ Done — `max_attempts=3, max_delay=20` vs `asyncio.timeout(110s)` |
| Error handling / fallback on agent error | ✅ Done — `finally: yield done` in `chat.py` |
| Streaming via `stream_async()` | ✅ Done |
| Token usage monitoring | ✅ Done — `TokenMetricsHook` (EMF + structured log) |
| Tool execution metrics | ✅ Done — `TokenMetricsHook.tool_stats` per invocation |

**Note on explicit model config:** Previously deferred, now set. The Strands production docs explicitly recommend explicit `temperature`/`max_tokens`/`top_p` so agent behavior doesn't silently shift if Bedrock updates provider defaults.

---

### AWS Lambda deployment — `[LOW / Already Done]`

The official Strands Lambda layer exists (`arn:aws:lambda:us-east-1:856699698935:layer:strands-agents-py3_11-aarch64:1`) but we already bundle `strands-agents` via the SST Python bundler (uv). No change needed — our packaging approach is equivalent and gives more control over versions.

**One gap noted in docs:** The Strands Lambda guide recommends **establishing a new MCP connection per invocation** (not reusing module-level connections) to prevent state leakage between users. Not relevant to us since we don't use MCP tools, but worth knowing if MCP tools are added later.

---

### Versioning & Support — `[LOW]`

- Pin `strands-agents` to a minor version in `pyproject.toml` (e.g., `>=0.1.0,<0.2.0`) to avoid surprise breaking changes from `uv lock --upgrade`.
- The X-Ray SDK enters maintenance mode February 2026 — Powertools is tracking an OTEL provider migration. Follow the Strands GitHub releases for when their OTEL provider ships (currently on the p0 roadmap).

---

## Post-Plan Structural Changes

Changes made during implementation that weren't in the original plan:

**`backend/app/agent/` package refactor (`eaca11c`):** `agent.py` was split into:
- `agent/core.py` — `BedrockModel`, `RETRY_STRATEGY`, `TOOLS` module-level singletons
- `agent/hooks.py` — `CorrelationIdHook`, `TokenMetricsHook`, `LimitToolCallsHook`
- `agent/prompts.py` — `SYSTEM_PROMPT` constant

**Bedrock guardrail infra fixes (`b9e36c1`):** Required fields (`blockedInputMessaging`, `blockedOutputsMessaging`) were missing from the initial `aws.bedrock.Guardrail` resource; added.

**WAF removed (`e1b8224`):** `aws.wafv2.WebAclAssociation` is not supported on Lambda Function URLs — only ALB and CloudFront. WebACL was created but association silently fails. Removed from `infra/security.ts`.

**60-day booking window + past-date validation (`c5eddb1`):** `SYSTEM_PROMPT` hardened with explicit booking constraints — no dates in the past, no dates more than 60 days out.

**`restaurant_name` optional in `get_booking_details` (`0f8387e`):** Made optional in the tool signature; repository lookup falls back gracefully. Fixes cases where the agent omits it when it already has the booking ID.

**`config.py` guardrail link guard (`835a0ba`):** Wrapped `Resource.RestaurantGuardrail` in `try/except` — the SST link is inactive when the guardrail resource is not deployed (staging without guardrail), preventing import errors.

---

## What This Codebase Has (Do Not Duplicate)

| What | Where | Notes |
|---|---|---|
| `asyncio.timeout(110s)` | `chat.py` | Aligned with `ModelRetryStrategy.max_delay=20` |
| Lambda Powertools Logger | `app/logging.py` | JSON, `cold_start`, `xray_trace_id`, correlation ID — keep |
| Lambda Powertools Metrics | `app/metrics.py` | `ChatRequest`, `AgentError`, `BookingCreated` — extend, don't replace |
| Lambda Powertools Tracer | `app/tracer.py`, `tools/bookings.py` | DynamoDB subsegments + `agent.stream` subsegment |
| `GUARDRAIL_ID` / `GUARDRAIL_VERSION` | `config.py`, `agent/core.py` | Injected via SST link; omitted gracefully in local dev |
| `_PiiRedactionFilter` | `app/logging.py` | Regex filter on root + Powertools logger; scrubs email/phone |
| Pydantic input validation | `models/schemas.py` | API boundary validation — complementary to prompt hardening |
| `force_stop` detection | `chat.py` | Covers guardrail interventions (`stop_reason="guardrail_intervened"`) |
