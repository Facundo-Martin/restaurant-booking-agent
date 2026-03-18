# Enhancing Observability and Evaluations

> **Status: Phase 1 (evaluators) ready to implement. Phase 2 (platform migration) is research / decision pending.**

---

## Phase 1 — Missing Strands Evaluators (Implement First)

The current eval suite has two files:
- `trajectory_eval.py` — verifies the agent calls the right tools in the right order
- `advanced_eval.py` — boilerplate placeholder, not yet implemented

Three evaluators from the Strands Evals SDK directly address gaps in the current booking agent and should be added before any observability platform work. They are independent, don't require Arize, and run in CI today.

### Why these three matter

| Evaluator | Level | Gap it fills |
|---|---|---|
| `FaithfulnessEvaluator` | TRACE | Detects RAG hallucination — agent inventing restaurants/menu items not in the knowledge base |
| `GoalSuccessRateEvaluator` | SESSION | Measures end-to-end booking completion — did the user actually get a confirmed booking? |
| `ToolParameterAccuracyEvaluator` | TOOL | Catches hallucinated booking parameters — wrong date, wrong party size, wrong restaurant name passed to `create_booking` |

The trajectory eval already checks *which* tools fire and *in what order*. These three check *what the tools were given* and *whether the outcome was correct* — entirely different signal.

---

### 1. `FaithfulnessEvaluator` — RAG Hallucination Detection

**What it catches:** The agent invents facts not present in the knowledge base response — e.g., claims a restaurant is open on Mondays when the KB says it's closed, or mentions dishes not in the menu.

**Why it matters:** The `retrieve` tool returns raw knowledge base text. The model synthesizes a response from that text. Faithfulness measures whether the response is grounded in the retrieval result. This is the primary failure mode for RAG systems.

**Evaluator level:** TRACE (evaluates a single agent invocation and its retrieval context)

**Implementation outline (`tests/evals/faithfulness_eval.py`):**

```python
from strands_evals import Case, Experiment
from strands_evals.evaluators import FaithfulnessEvaluator

# Faithfulness compares the agent's final response against the retrieved context.
# Cases must provide both the user query and the expected retrieval context so
# the judge can determine whether the answer is grounded.
test_cases = [
    Case[str, str](
        name="faithfulness-closed-monday",
        input="Is Bistro Parisienne open on Mondays?",
        # ground_truth is the retrieval context the agent should have used.
        # The evaluator checks: does the response faithfully reflect this?
        ground_truth="Bistro Parisienne (French, closed Mondays, accepts reservations)",
        metadata={"category": "faithfulness"},
    ),
    Case[str, str](
        name="faithfulness-italian-only",
        input="What Italian restaurants do you have?",
        ground_truth=(
            "Available restaurants: Nonna's Hearth (Italian), "
            "Bistro Parisienne (French), Sakura Garden (Japanese)"
        ),
        # Agent should mention only Nonna's Hearth — not hallucinate other Italian places.
        metadata={"category": "faithfulness"},
    ),
    Case[str, str](
        name="faithfulness-no-invented-hours",
        input="What time does Sakura Garden open?",
        ground_truth="Sakura Garden (Japanese, open daily, accepts reservations)",
        # KB doesn't mention opening hours — agent should not invent a specific time.
        metadata={"category": "faithfulness"},
    ),
]

evaluator = FaithfulnessEvaluator(model=_JUDGE_MODEL)
```

**Key test design rule:** Include cases where the KB *doesn't* contain the answer. The agent should admit uncertainty, not fill in plausible-sounding details. Faithfulness score < 1.0 on those cases is a hallucination.

---

### 2. `GoalSuccessRateEvaluator` — End-to-End Booking Completion

**What it catches:** Multi-turn conversations where the agent technically follows the tool trajectory but fails to land the user on a confirmed booking. Trajectory eval checks steps; goal success checks outcomes.

**Why it matters:** A user might receive the right tool calls (current_time → retrieve → create_booking) but still not get a booking — e.g., the agent summarizes the booking incorrectly, doesn't confirm clearly, or goes off-script mid-flow. Goal success is the only metric that directly measures whether the product *works*.

**Evaluator level:** SESSION (evaluates a full multi-turn conversation, not a single turn)

**Implementation outline:**

```python
from strands_evals.evaluators import GoalSuccessRateEvaluator

# GoalSuccessRateEvaluator needs multi-turn conversation histories.
# Each case provides a complete conversation and a success criterion.
booking_conversation = [
    {"role": "user", "content": "I want to book a table at Nonna's Hearth for 2 people on March 20th"},
    {"role": "assistant", "content": "I'll check availability and create a booking for you."},
    # ... intermediate turns ...
    {"role": "assistant", "content": "Your booking is confirmed! Booking ID: B-456, "
        "Nonna's Hearth, March 20th, party of 2."},
]

test_cases = [
    Case(
        name="goal-booking-confirmed",
        input=booking_conversation,
        ground_truth="User successfully received a confirmed booking with ID, restaurant, date, and party size.",
        metadata={"category": "goal-success"},
    ),
    Case(
        name="goal-clarification-then-booking",
        input=[
            {"role": "user", "content": "Book me a table tonight"},
            {"role": "assistant", "content": "I'd be happy to help! Which restaurant, what time, and how many guests?"},
            {"role": "user", "content": "Nonna's Hearth, 7pm, just me"},
            # agent should resolve date, check restaurant, confirm booking
        ],
        ground_truth="User received a confirmed booking after providing clarification details.",
        metadata={"category": "goal-success"},
    ),
    Case(
        name="goal-cancellation-confirmed",
        input=[
            {"role": "user", "content": "Cancel booking B-456"},
            # agent should confirm cancellation clearly
        ],
        ground_truth="User received confirmation that booking B-456 was cancelled.",
        metadata={"category": "goal-success"},
    ),
]

evaluator = GoalSuccessRateEvaluator(model=_JUDGE_MODEL)
```

**Note on SESSION-level eval:** `GoalSuccessRateEvaluator` is designed for multi-turn conversations. Single-turn evals (like trajectory_eval.py) capture one request; goal success captures whether a complete user journey succeeded. These don't overlap — both are needed.

---

### 3. `ToolParameterAccuracyEvaluator` — Hallucinated Booking Parameters

**What it catches:** The agent calls `create_booking` with parameters that don't match what the user specified — e.g., calls with `party_size=4` when user said "2 people", or `date="2026-03-21"` when user said "20th", or `restaurant_name="Nonna Hearth"` (abbreviated) instead of the exact name in the KB.

**Why it matters:** Trajectory eval confirms `create_booking` is called. This confirms it's called with *correct* arguments. A wrong booking is worse than no booking — the user may not notice until they arrive at the restaurant.

**Evaluator level:** TOOL (evaluates the inputs and outputs of individual tool calls)

**Implementation outline:**

```python
from strands_evals.evaluators import ToolParameterAccuracyEvaluator

test_cases = [
    Case(
        name="param-accuracy-party-size",
        input="Book a table for 2 at Nonna's Hearth on March 20th",
        # Expected tool call parameters — evaluator checks agent's actual call matches
        expected_tool_call={
            "tool_name": "create_booking",
            "parameters": {
                "party_size": 2,
                "restaurant_name": "Nonna's Hearth",
                # date is resolved at runtime; test that it's not hallucinated
            },
        },
        metadata={"category": "param-accuracy"},
    ),
    Case(
        name="param-accuracy-exact-restaurant-name",
        input="Book me a table at Nonna's Hearth for 3 people next Friday",
        expected_tool_call={
            "tool_name": "create_booking",
            "parameters": {
                "restaurant_name": "Nonna's Hearth",  # exact KB name, not abbreviated
                "party_size": 3,
            },
        },
        metadata={"category": "param-accuracy"},
    ),
    Case(
        name="param-accuracy-booking-id-lookup",
        input="What are the details for booking B-456?",
        expected_tool_call={
            "tool_name": "get_booking_details",
            "parameters": {"booking_id": "B-456"},
        },
        metadata={"category": "param-accuracy"},
    ),
]

evaluator = ToolParameterAccuracyEvaluator(model=_JUDGE_MODEL)
```

---

### Implementation order and file layout

Implement as three separate eval files (same pattern as `trajectory_eval.py`):

```
backend/tests/evals/
├── trajectory_eval.py       # ✅ exists
├── faithfulness_eval.py     # implement first (simplest, no multi-turn needed)
├── goal_success_eval.py     # implement second (requires multi-turn test data)
├── tool_param_eval.py       # implement third (requires actual tool call inspection)
└── advanced_eval.py         # boilerplate placeholder — refactor into above files
```

All three use the same `_JUDGE_MODEL` (Haiku), same `_FAKE_RESTAURANTS` / `_FAKE_BOOKING` constants from `trajectory_eval.py`, same `asyncio.Semaphore(2)` concurrency cap. Factor shared fixtures into a `conftest.py` or a `_shared.py` module.

### Relationship to Arize / Phase 2

These Strands Evals evaluators are **offline CI evals** — they run against staged test cases in GitHub Actions before deploy. Arize's online evals run against *live production traffic* after deploy. They are complementary, not redundant:

- Strands Evals catches regressions *before* they reach production (shift-left)
- Arize online evals catch issues that only appear on *real user traffic* (production drift)

Implement Phase 1 regardless of whether Phase 2 (Arize) is adopted. The CI coverage is valuable on its own.

---

## Where We Are Now

From the `taking-strands-to-production.md` work, the stack already has:

| Layer | What's in place |
|---|---|
| Traces | Langfuse Cloud (OTLP HTTP) via `StrandsTelemetry().setup_otlp_exporter()` |
| Span semantics | Strands native OTEL spans — basic, not OpenInference |
| Metrics | CloudWatch EMF via `TokenMetricsHook` (InputTokens, OutputTokens, AgentCycles) |
| Structured logs | `agent_invocation_complete` per-request JSON in CloudWatch Logs |
| Offline evals | Strands Evals SDK: `FaithfulnessEvaluator`, `TrajectoryEvaluator` in pytest CI |
| Online evals | None — no live-traffic evaluation |

The two gaps worth closing:
1. **Richer span semantics** — current OTEL spans lack LLM-specific OpenInference attributes (input/output token details, prompt/completion separation, tool call semantics in a standard schema)
2. **Online evaluations** — no mechanism to automatically evaluate live production traffic; issues only surface via user complaints or manually triggered eval runs

---

## The Platform Landscape

### Arize AX

Arize is the most mature purpose-built LLM observability and evaluation platform. Key facts:

**Technical model:** OpenInference standard on top of OpenTelemetry. OpenInference is an open spec defining semantic conventions for LLM spans — it adds `llm.input_messages`, `llm.output_messages`, `llm.token_count.*`, `tool.name`, `retrieval.documents`, etc. on top of bare OTEL spans. Arize ingests these, not raw OTEL.

**Strands integration path:** Two layers:
1. `openinference-instrumentation-strands-agents` — a span processor (`StrandsAgentsToOpenInferenceProcessor`) that converts Strands' internal OTEL spans to OpenInference format before export
2. OTLP exporter pointing to `otlp.arize.com:443` (gRPC) or `https://otlp.arize.com/v1` (HTTP)

Session and user IDs are passed via `trace_attributes` on the Agent, same as we already do for Langfuse:
```python
trace_attributes={
    "session.id": request.session_id or get_correlation_id(),
    "arize.tags": [APP_STAGE],
    "user.id": "...",  # optional
}
```

**What you get that Langfuse doesn't:**
- **Online evaluations** — LLM-as-judge evals that run automatically on every trace in production without manual trigger. You define a rubric once in the UI; Arize runs it against new traces as they arrive. This is the single most compelling feature.
- **Session-level evaluations** — session correctness, user frustration detection, goal achievement scoring — aggregated across multi-turn conversations, not just individual spans
- **OpenInference span semantics** — richer, standardized LLM attributes make the trace timeline actually interpretable: you can read the full input/output in the trace view, not just raw JSON
- **Trace-to-eval linkage** — eval scores are stored alongside traces, so you can filter traces by score (e.g., "show me all sessions where trajectory score < 0.8")

**Pricing:**
| Tier | Cost | Spans/month | Retention |
|---|---|---|---|
| Phoenix OSS | Free, self-host | Unlimited | Self-managed |
| AX Free | Free | 25K | 7 days |
| AX Pro | $50/month | 50K | 15 days |
| AX Enterprise | Custom | Custom | Configurable |

25K spans/month on the free tier: a restaurant booking agent making 10–50 real requests/day generates maybe 500–2,500 spans/day (each request = 1 agent span + 3-5 tool spans). Free tier covers ~10–50 real users/day comfortably.

**Lambda-specific concern (important):**
The notebook integration uses `BatchSpanProcessor` with gRPC OTLP. In Lambda, this is a real problem: `BatchSpanProcessor` flushes asynchronously in background threads; Lambda may freeze the execution environment after the response is returned before the batch flush completes, silently dropping spans.

**The fix:** Either:
- Use `SimpleSpanProcessor` (synchronous, flush on every span — adds latency but guaranteed)
- Call `tracer_provider.force_flush()` before the Lambda handler returns
- Use the HTTP OTLP endpoint (`https://otlp.arize.com/v1`) instead of gRPC + `SimpleSpanProcessor`

This is a solvable problem but requires explicit handling — it won't just work out of the box with the notebook pattern.

**Arize Phoenix (OSS):** If you don't want to pay and don't want vendor lock-in, Phoenix is the self-hosted open-source version of Arize. Same OpenInference semantics, same UI. Runs as a Docker container. For a side project this is actually the right call — you get the full observability platform for free, no 25K span/month limit, but you have to run the infra.

---

### Amazon Bedrock AgentCore Observability

AgentCore Observability is CloudWatch-powered agent monitoring built into the AgentCore platform. It provides:
- CloudWatch traces, metrics, logs for agent runs
- Quality evaluations: correctness, helpfulness, safety, goal success rate (LLM-as-judge)
- OTEL-compatible — can export to external tools
- Session tracking, token usage, latency, error rates

**The critical constraint: it's tied to AgentCore Runtime.**

AgentCore Observability is a feature of the AgentCore deployment platform, not a standalone monitoring service. To use it, your agent needs to be deployed via `AgentCore Runtime`, not Lambda. Migrating from our Lambda/SST deployment to AgentCore Runtime would mean:
- Abandoning the SST deployment pipeline
- Rewriting the deployment model (AgentCore Runtime has different invocation patterns)
- Losing our current Lambda-based SSE streaming setup (AgentCore has its own streaming model)
- Taking on a new platform with less community support and documentation

**Bottom line: AgentCore Observability is not applicable to our current architecture.** It's relevant only if you decide to migrate the entire deployment to the AgentCore platform. That's a separate and much larger decision, not an observability add-on.

---

### Opik (Comet ML)

Opik is a genuinely open-source LLM observability platform. Key differentiators:

- Self-hostable via Docker or Kubernetes (no vendor lock-in, no per-span billing)
- Supports Strands Agents, OTEL, 50+ integrations
- Has a `@track` decorator similar to Langfuse's `@observe`
- Evaluation, monitoring dashboards, CI/CD integration via pytest
- Scales to 40M+ traces/day
- Managed cloud version on Comet.com

**Honest assessment:** Opik is excellent for teams that want self-hosted, no-cost observability. But it's less mature than Arize for LLM-specific features — the online eval story is less compelling, and the OpenInference span semantics integration isn't as deep. For a team already invested in the AWS/Bedrock ecosystem, there's no particular advantage over either Arize Phoenix (OSS) or Langfuse.

---

### MLflow

MLflow is a surprise entry here — it's primarily known as an MLOps/experiment-tracking platform but has invested heavily in LLM observability since v2.13 and has a **native `mlflow.strands.autolog()` integration**.

**What it actually does for Strands:**
One line enables full auto-tracing:
```python
import mlflow
mlflow.strands.autolog()  # captures all agent invocations automatically
```
Captures: prompts + completion responses, request latencies, token usage + cost, cache hits, agent metadata (function names), and exceptions. `mlflow.bedrock.autolog()` adds a second layer for direct Bedrock API calls (via boto3 `converse`/`invoke_model` — streaming included).

**What's genuinely good:**
- 100% free and open-source — no span limits, no retention limits
- OTEL-compatible — existing OTEL infrastructure integrates with it
- The `mlflow-tracing` lightweight SDK reduces Lambda cold-start footprint by 95% vs full MLflow
- Async logging available to avoid blocking the request path
- Experiment tracking: compare prompt versions, model versions side-by-side — useful if you're iterating on the system prompt
- Managed hosting on Amazon SageMaker (relevant since we're AWS-native, though not free)

**What's not good for our use case:**
- MLflow's primary identity is **ML experiment tracking** (model training runs, hyperparameter comparison). LLM observability is a newer addition built on top of that mental model. The UI reflects this — it's an experiments/runs tracker that happens to show LLM traces, not an LLM-first observability product.
- **No online evaluations** — there's no equivalent to Arize's automatic live-traffic LLM-as-judge. Evaluations in MLflow are offline: you run `mlflow.evaluate()` against a dataset. Useful for CI, but not for live traffic.
- **No session-level analysis** — sessions exist as a concept but there's no dedicated session timeline view or session-level eval aggregation.
- **No OpenInference semantics** — MLflow uses its own span schema. Spans are readable but not the OpenInference standard that Arize and Phoenix share.
- **Self-hosting = real infra** — the MLflow tracking server needs a backend store (Postgres/SQLite) and artifact store (S3). More operational overhead than Langfuse cloud or Arize free tier.

**Honest verdict:** MLflow is the right choice if you're already in a Databricks ecosystem, doing traditional ML training alongside LLM work, or need SageMaker integration. For a pure Strands + Lambda + Bedrock stack focused on production observability and online evals, it's the wrong tool. The `autolog()` one-liner is elegant, but the overall platform is solving a different problem (experiment tracking) than what we actually need (live traffic evaluation and session analysis).

---

### Langfuse (current)

Already implemented. Key characteristics:
- HTTP OTLP export — Lambda-friendly, no BatchSpanProcessor issues
- Session grouping via `session.id` attribute — already working
- Stores Strands Evals SDK scores alongside traces (future linkage)
- Free tier is generous (no hard span limit, 30-day retention on free)
- Good prompt management UI
- No online evaluations without additional integration
- Spans are basic OTEL without OpenInference semantics — less readable in the UI

---

## Honest Assessment

**The gap that actually matters is online evaluations, not tracing UI.**

The current Langfuse tracing gives adequate production visibility for a restaurant booking agent. You can see session timelines, token counts, tool calls. The spans aren't OpenInference-enriched so they're a bit raw, but they're functional.

What the current stack genuinely lacks is **automatic evaluation of live traffic**. The Strands Evals SDK runs nightly in CI against staged test cases — good for regression testing but not for detecting production drift (prompt changes that silently degrade booking success rates, users asking things the agent handles poorly, etc.). Without online evals, issues only surface reactively.

**The case for adding Arize AX:**

1. Online evaluations on live traffic are genuinely the biggest observability gap
2. OpenInference semantics meaningfully improve trace readability (you can read the actual LLM conversation in the trace view)
3. Session-level evals map directly to our use case (booking flow completion, user frustration detection)
4. The Strands integration is officially documented and AWS-published — not experimental
5. Free tier covers our traffic volume without cost
6. Can coexist with Langfuse (two OTLP exporters) or replace it

**The case against adding Arize AX (be honest about this):**

1. **We already have Langfuse working.** Adding Arize creates two sinks for the same data — cognitive overhead, two dashboards to check, two sets of configs to maintain
2. **Lambda compatibility requires custom work.** The notebook pattern (BatchSpanProcessor + gRPC) will silently drop spans on Lambda. Needs `SimpleSpanProcessor` and careful flush handling in the generator's `finally` block
3. **The OpenInference processor adds cold start weight.** `openinference-instrumentation-strands-agents` adds a package and a span processor to the Lambda cold start path
4. **25K spans/month is surprisingly easy to exhaust** if you add CI/eval runs to the same project — eval traces count against the limit
5. **Online evals cost money to run** (they call an LLM on every trace) — on the free tier this means Arize is running evaluations that you pay for indirectly via Bedrock costs if you configure them to use your own model

**The case for AgentCore Observability:**

Essentially none, for this deployment. Unless you're willing to migrate the entire stack to AgentCore Runtime, this isn't available to you. Don't confuse "it's on AWS" with "it works with Lambda + Strands."

---

## Recommendation

**Replace Langfuse with Arize AX Free (or Arize Phoenix OSS if self-hosting is acceptable).**

Don't run both. The observability value isn't additive enough to justify two platforms.

**Why replace rather than supplement:** Langfuse's core value is the tracing UI and prompt management. Arize AX does everything Langfuse does, better, with the addition of online evals. Running both means maintaining two OTLP exporters, two sets of API keys, two sets of retention rules, and checking two dashboards. It's overhead with no clear benefit.

**Why Arize over Langfuse:** Online evals is the deciding factor. It's the one feature that provides genuine production feedback that the current stack can't get any other way. Everything else (traces, session grouping, token metrics) we already have.

**Why not Phoenix OSS:** Only if you're unwilling to take on self-hosting overhead. Phoenix OSS running on a cheap EC2/ECS instance is zero cost with no span limits. But it's infra to manage. For a side project the free Arize AX cloud tier is simpler.

**The AgentCore migration question is separate.** If you ever migrate to AgentCore Runtime for other reasons (e.g., built-in memory, multi-agent orchestration, AgentCore Gateway), AgentCore Observability comes with it. That's a future decision. Don't let it block observability improvements now.

---

## Implementation Plan (if proceeding with Arize AX)

### Step 1 — Verify Lambda compatibility before committing

Create a feature branch. Wire up Arize with `SimpleSpanProcessor` (not `Batch`) and confirm spans arrive in Arize from a local test. Then deploy to staging and verify no spans are dropped.

The key thing to test: does a Lambda invocation's spans arrive in Arize when the SSE stream completes? The `finally` block in `chat.py` is the flush point.

### Step 2 — Add dependencies

`backend/pyproject.toml`:
```toml
[project.optional-dependencies]
observability = [
    "openinference-instrumentation-strands-agents",
    "opentelemetry-exporter-otlp-proto-http",  # HTTP not gRPC — Lambda-safe
]
```

### Step 3 — Replace telemetry setup in `main.py`

Remove the `StrandsTelemetry().setup_otlp_exporter()` call. Replace with:
```python
if _in_lambda and os.environ.get("ARIZE_API_KEY"):
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # not Batch
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from openinference.instrumentation.strands_agents import StrandsAgentsToOpenInferenceProcessor

    provider = TracerProvider()
    provider.add_span_processor(StrandsAgentsToOpenInferenceProcessor())
    provider.add_span_processor(
        SimpleSpanProcessor(
            OTLPSpanExporter(
                endpoint="https://otlp.arize.com/v1/traces",
                headers={
                    "space_id": os.environ["ARIZE_SPACE_ID"],
                    "api_key": os.environ["ARIZE_API_KEY"],
                },
            )
        )
    )
    trace.set_tracer_provider(provider)
```

**Note:** `SimpleSpanProcessor` means every span is exported synchronously. This adds latency — measure it. The alternative is `BatchSpanProcessor` + explicit `provider.force_flush()` in `chat.py`'s `finally` block, which is more complex but lower latency.

### Step 4 — Update `trace_attributes` in `chat.py`

```python
trace_attributes={
    "session.id": request.session_id or get_correlation_id(),
    "arize.tags": [APP_STAGE],
    "user.id": request.session_id or "anonymous",  # Arize session grouping
}
```

### Step 5 — Store secrets in SST

```typescript
// infra/api.ts
const arizeApiKey = new sst.Secret("ArizeApiKey");
const arizeSpaceId = new sst.Secret("ArizeSpaceId");
```

Set via: `npx sst secret set ArizeApiKey <value>`

### Step 6 — Remove Langfuse env vars from `infra/api.ts`

Clean out `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_TRACES_SAMPLER*`.

### Step 7 — Configure online evaluations in Arize UI

After traces start arriving:
- Set up a `Trajectory Correctness` online eval: rubric matching `tests/evals/trajectory_eval.py`'s criteria
- Set up a `Goal Success` eval: "Did the user successfully complete a booking or get the info they needed?"
- Set `evaluation_sampling_rate=0.1` in production (10% of traces evaluated) to manage costs

---

## Risks and Open Questions

| Risk | Severity | Notes |
|---|---|---|
| `SimpleSpanProcessor` latency overhead | Medium | Measure in staging — each span exported synchronously adds RTT to the request |
| 25K span/month free tier exhaustion | Low | ~500–2,500 spans/day = 15K–75K/month. Might hit limit under load |
| OpenInference processor maintenance | Low | Package is maintained by Arize; tied to Strands SDK versioning |
| Two-platform migration rollback | Low | Langfuse config is one env var change away if Arize doesn't work out |
| Online eval LLM costs | Low | Arize runs evals on their infra at their cost (on Free/Pro tiers) — no Bedrock cost |

**Unresolved:** Does `StrandsAgentsToOpenInferenceProcessor` work correctly with `stream_async()`? The notebook tests use synchronous `agent(...)` calls. Our production path is `agent.stream_async()` — span lifecycle may differ. Needs testing.

---

## Sources

- [Strands + Arize OpenInference notebook](https://github.com/strands-agents/samples/blob/main/03-integrations/Openinference-Arize/Arize-Observability-openinference-strands.ipynb) — official integration reference
- [Arize: Guide to trace-level LLM evaluations](https://arize.com/blog/guide-to-trace-level-llm-evaluations-with-arize-ax/) — trace vs span eval distinction
- [Arize: Session-level evaluations](https://arize.com/blog/session-level-evaluations-with-arize-ax/) — session correctness, frustration, goal achievement
- [Arize pricing](https://arize.com/pricing/) — tier details
- [AgentCore product page](https://aws.amazon.com/bedrock/agentcore/) — confirms OTEL integration + CloudWatch backing
- [Opik GitHub](https://github.com/comet-ml/opik) — OSS alternative overview
- [No Safe Words (Substack)](https://mercurialsolo.substack.com/p/no-safe-words) — honest production failures: "70% of live agent deployments still hit loops/goal-drift/privilege-spikes"; multi-layer safety + observability is the only reliable mitigation
- [MLflow GitHub](https://github.com/mlflow/mlflow) — OSS ML platform with native Strands autolog
- [MLflow Strands integration docs](https://mlflow.org/docs/latest/genai/tracing/integrations/listing/strands.html) — `mlflow.strands.autolog()` reference
- [MLflow Bedrock integration docs](https://mlflow.org/docs/latest/genai/tracing/integrations/listing/bedrock.html) — boto3-level Bedrock tracing
