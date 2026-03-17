# Taking the Backend Toward Production

> **Status: sections 4–12, 14, and 15 implemented. Branch ready to PR.**

References:
- [Preparing FastAPI for Production](https://medium.com/@ramanbazhanau/preparing-fastapi-for-production-a-comprehensive-guide-d167e693aa2b)
- [FastAPI Best Practices (zhanymkanov)](https://github.com/zhanymkanov/fastapi-best-practices)

---

## Architecture Quick-Reference

_Before diving in, the backend has two distinct entry points that behave differently for auth, rate limiting, and observability:_

| | **Chat** | **Bookings / Health** |
|---|---|---|
| Entry point | Lambda Function URL | API Gateway v2 |
| Handler | `handler_chat.py` + Lambda Web Adapter (LWA) | `handler_bookings.py` + Mangum |
| Streaming | LWA starts uvicorn; streams response back | Standard request/response |
| Timeout / memory | 120s / 1024 MB | 10s / 256 MB |
| Auth (planned) | FastAPI JWT middleware | API Gateway JWT authorizer |
| Rate limiting (planned) | WAF on Function URL | WAF on API Gateway |

_Every section below must be read with this split in mind. A change that "just works" for the bookings routes may need a different approach for the chat Function URL._

---

## 1. Introduction

_What "production" means in this context. The backend already runs on Lambda — this guide covers what separates a working demo from a service you'd put real traffic on._

_Three axes of production readiness:_
- _**Observability** — you can see what's happening and reconstruct any failure from logs._
- _**Resilience** — the service fails gracefully: bounded latency, sanitized errors, no internal detail leaks._
- _**Operability** — you can deploy, roll back, and iterate with confidence via an automated pipeline._

_Prerequisites: completed `how-to-build-backend.md`. The backend is deployed and the SSE chat endpoint works end-to-end._

---

## 2. Decision Log

_The "not sure" items from the initial plan, resolved. Read this section before touching any code._

### 2a. Authorization — Cognito, deferred to its own phase

_Why not DIY JWTs: building auth infrastructure from scratch (token issuance, refresh, password reset, MFA) is a project in itself and not the focus here._

_Why Cognito: it's the AWS-native identity provider and integrates directly with API Gateway v2's JWT authorizer — tokens are validated before the request reaches Lambda, at zero application code cost. SST has first-class `sst.aws.CognitoUserPool` support._

_The complication: the chat endpoint is a **Function URL**, which has no native JWT authorizer. API Gateway's authorizer only covers the bookings/health routes. For the chat endpoint, JWT validation must happen in FastAPI middleware. This asymmetry is the main reason auth is its own phase — it requires coordinated changes across infra, backend, and the frontend login flow. Section 12 stubs this phase._

_Immediate implication: `Booking.user_id` is currently a plain string passed by the client — not tied to any authenticated identity. That changes in the auth phase._

### 2b. Rate limiting — AWS WAF, infra only

_Why not `slowapi` / Redis: rate limiting in the application layer requires shared state across Lambda instances. That means ElastiCache Redis — a persistent network resource that adds cost, operational overhead, and a new failure mode. Not worth it._

_Why not API Gateway throttling alone: the chat endpoint is a Function URL, bypassing API Gateway entirely. API Gateway throttling does not apply to it._

_Decision: **AWS WAF web ACL attached to both API Gateway and the Function URL**. WAF supports rate-limiting rules by IP, geo-blocking, known bad input patterns, and SQL injection detection — all without application code. `infra/api.ts` already has a `TODO: Attach WAF once the frontend domain is known`. Section 11 implements it._

### 2c. Caching — skip

_`/chat` — not cacheable. Every request is a unique conversation turn._
_`GET /bookings/{id}` — technically cacheable, but a booking can be deleted at any time. Cache invalidation on delete is complex for zero benefit at this scale._
_Module-level singletons (`BedrockModel`, `_table`, `TOOLS`) already cache the expensive initializations. That's all the caching this service needs._

### 2d. Logging — Lambda Powertools Logger

_Evaluated: standard `logging` + `python-json-logger` (lightweight, no Lambda context), `structlog` (flexible, more setup), Loguru (nice ergonomics, not Lambda-aware)._

_Decision: **`aws-lambda-powertools` Logger**. It emits JSON natively, auto-injects `cold_start`, `function_name`, `function_version`, and `xray_trace_id` into every log record, and is the same library used for tracing (Tracer) and metrics (Metrics). One dependency for three capabilities._

### 2e. Observability — CloudWatch + X-Ray via Lambda Powertools

_Evaluated: Grafana + Prometheus (requires a self-hosted metrics collector or Grafana Cloud subscription), Datadog/New Relic (third-party APM, adds cost and Lambda layer overhead), OpenTelemetry (standard protocol, more setup)._

_Decision: **CloudWatch Logs + X-Ray via Lambda Powertools Tracer + Metrics**. Zero additional infrastructure. X-Ray traces Lambda → DynamoDB → Bedrock Runtime automatically. CloudWatch custom metrics (ChatRequests, AgentErrors) are flushed at Lambda exit. Grafana/Prometheus are the right choice for self-hosted or multi-cloud — not for a Lambda-only stack._

### 2f. Containerization — skip

_Lambda Web Adapter (LWA) already solves the ASGI-in-Lambda problem via a layer — no Docker image needed. Zip deployment via uv/SST bundler is simpler, has faster cold starts, and is the correct default. Container images are appropriate when package size exceeds the 250 MB unzipped Lambda limit or when custom OS libraries are required. Neither applies here._

---

## 3. Codebase Audit

_What the current backend does well, and the specific gaps that drive the rest of this guide._

### 3a. What's already correct

_The folder structure (Approach B), the module-level singleton pattern for `BedrockModel`/`_table`/`TOOLS`, the per-request `Agent` creation, the `finally: done` SSE guarantee, the `AWS_LAMBDA_FUNCTION_NAME` guard on CORS, and the split handlers (`handler_chat.py` / `handler_bookings.py` sized differently) are all correct and do not change._

### 3b. Stale unit tests

_`tests/unit/test_api.py` is out of sync with the current implementation. It patches `app.api.routes.chat.get_agent` (this function does not exist — the route uses `agent.stream_async` directly) and expects a `{"response": ..., "session_id": ...}` JSON body (the actual route returns an SSE stream). These tests pass because the mock patches a missing import cleanly, masking that they test nothing._

_This must be fixed before any other work — stale tests that pass give false confidence. The chat route tests need to mock `agent.stream_async` and assert on the SSE event sequence._

### 3c. Open gaps by area

| Area | Current state | Gap |
|------|---------------|-----|
| Tests | `test_api.py` patches wrong targets | Tests pass but cover nothing real |
| Error handling | `str(exc)` in SSE events; FastAPI default 422 shape | Leaks internals; inconsistent error shape |
| Logging | `logging.getLogger()` — one line per request, plain text | No JSON; no correlation IDs; CloudWatch can't query by field |
| Input validation | Pydantic schema only | No max content length; expensive payloads reach Bedrock unchecked |
| Agent stream | No timeout on `stream_async` | Stream runs until 120s Lambda timeout on Bedrock hang |
| Security headers | None | Not set on any response |
| OpenAPI docs | Always exposed | `/docs` accessible on production Function URL |
| Observability | None | No X-Ray; no CloudWatch custom metrics |
| Health check | `{"status": "ok"}` liveness only | Dead DynamoDB table returns 200 |
| CORS | `allowOrigins: ["*"]` everywhere | Both API Gateway and Function URL accept any origin |
| WAF | Not attached | No rate limiting on the chat Function URL |
| CI/CD | None | Manual `sst deploy`; no quality gates |
| Auth | None | No identity; `user_id` is caller-supplied |

---

## 4. Fix Stale Tests ✅

The old `test_api.py` patched `app.api.routes.chat.get_agent` (a function that did not exist) and expected a `{"response": ..., "session_id": ...}` JSON body. Tests passed only because the mock silently swallowed the missing symbol — they covered nothing real.

**What changed:** full rewrite of `tests/unit/test_api.py`.

The key testing pattern for SSE routes:

```python
# Mock the Agent *class* — the route calls Agent(...) to create an instance,
# then calls instance.stream_async(message).
def make_mock_agent(events: list[dict]) -> MagicMock:
    async def _stream(_message: str):
        for event in events:
            yield event

    instance = MagicMock()
    instance.stream_async = _stream
    return MagicMock(return_value=instance)


def collect_sse_events(response) -> list[dict]:
    events = []
    for line in response.iter_lines():
        if line.startswith("data:"):
            payload = line[6:].strip()
            if payload:
                events.append(json.loads(payload))
    return events


def test_chat_text_delta():
    mock_agent = make_mock_agent([{"data": "Hello"}, {"data": "!"}])

    with patch("app.api.routes.chat.Agent", mock_agent):
        with client.stream("POST", "/chat", json=_VALID_CHAT_BODY) as response:
            events = collect_sse_events(response)

    assert [e["type"] for e in events] == ["text-delta", "text-delta", "done"]
```

Tests added: `test_chat_text_delta`, `test_chat_tool_cycle`, `test_chat_tool_error`, `test_chat_exception_yields_error_then_done`, `test_chat_force_stop_yields_error_then_done`, `test_chat_missing_messages_field`, `test_chat_message_content_too_long`, `test_chat_too_many_messages`, `test_chat_done_is_always_last`.

**Sources:**
- [FastAPI TestClient streaming](https://www.starlette.io/testclient/#streaming-responses)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)

---

## 5. Error Handling ✅

**Problem:** the original backend exposed `str(exc)` in SSE error events and returned FastAPI's raw Pydantic 422 shape — inconsistent across surfaces and leaking internal exception messages to clients.

**What changed:**

`app/exceptions.py` — machine-readable error codes alongside HTTP status:

```python
class AppException(HTTPException):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message

# Usage in routes:
raise AppException(status_code=404, code="BOOKING_NOT_FOUND", message=f"Booking {booking_id} not found.")
```

`app/models/schemas.py` — universal error envelope:

```python
class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None  # correlation ID, populated by middleware

class ErrorResponse(BaseModel):
    error: ErrorDetail
```

`app/main.py` — four global handlers covering every error surface:

```python
@app.exception_handler(AppException)
async def app_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code,
        content=ErrorResponse(error=ErrorDetail(
            code=exc.code, message=exc.message, request_id=get_correlation_id()
        )).model_dump())

@app.exception_handler(HTTPException)          # FastAPI internals (405, etc.)
@app.exception_handler(RequestValidationError) # Pydantic 422
@app.exception_handler(Exception)             # catch-all — never leaks str(exc)
```

SSE error events in `chat.py` sanitized to a generic message:

```python
except Exception:
    logger.exception("Agent stream error", extra={"correlation_id": get_correlation_id()})
    yield ServerSentEvent(data=json.dumps({"type": "error", "error": "An unexpected error occurred."}))
```

**Sources:**
- [FastAPI exception handlers](https://fastapi.tiangolo.com/tutorial/handling-errors/)
- [Starlette RequestValidationError](https://www.starlette.io/exceptions/)

---

## 6. Input Validation Hardening ✅

**Problem:** Pydantic stopped malformed requests but not expensive ones. A caller could send 200 messages with 100k characters each — all of it reaching Bedrock unchecked.

**What changed:**

Constants centralised in `app/config.py` so limits are tunable in one place:

```python
CHAT_MAX_MESSAGE_LENGTH: int = 4096   # characters per individual message
CHAT_MAX_MESSAGES: int = 50           # messages per /chat request
BOOKING_MAX_SPECIAL_REQUESTS_LENGTH: int = 500
```

`app/models/schemas.py` — constraints on all input fields:

```python
class ChatApiMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=CHAT_MAX_MESSAGE_LENGTH)

class ChatApiRequest(BaseModel):
    messages: list[ChatApiMessage] = Field(max_length=CHAT_MAX_MESSAGES)

class Booking(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")   # ISO 8601 — rejects "next tuesday"
    party_size: int = Field(ge=1, le=20)
    special_requests: str | None = Field(default=None, max_length=BOOKING_MAX_SPECIAL_REQUESTS_LENGTH)
```

Pydantic raises `RequestValidationError` on violation → the global handler returns HTTP 422 with the standard `ErrorResponse` envelope. Constraints also propagate to the OpenAPI spec and the generated TypeScript client automatically.

**Sources:**
- [Pydantic Field constraints](https://docs.pydantic.dev/latest/concepts/fields/)
- [FastAPI request validation](https://fastapi.tiangolo.com/tutorial/body-fields/)

---

## 7. Logging ✅

**Problem:** `logging.getLogger()` emitted plain-text lines with no JSON structure, no Lambda context, and no way to correlate log lines from the same request in CloudWatch.

### 7a. Lambda Powertools Logger

`app/logging.py` — single shared instance (prevents divergent service names):

```python
from aws_lambda_powertools import Logger
logger = Logger(service="restaurant-booking")
```

All modules import from here: `from app.logging import logger`. Emits structured JSON automatically, with `cold_start`, `function_name`, `function_version`, and `xray_trace_id` injected on every line when running in Lambda.

`handler_bookings.py` — `inject_lambda_context` enriches all log lines from that invocation with the Lambda request ID:

```python
@logger.inject_lambda_context(log_event=False, clear_state=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: LambdaEvent, context: LambdaContext) -> dict:
    return _mangum_handler(event, context)
```

`log_event=False` — the raw API Gateway event contains headers and body; logging it would expose sensitive data. `clear_state=True` — prevents `append_keys()` values from leaking across warm invocations.

`inject_lambda_context` only applies to `handler_bookings` — the chat Lambda runs under LWA+uvicorn where the Python handler is bypassed entirely.

### 7b. Correlation ID middleware

`app/middleware.py` — `ContextVar` is the right primitive here (not a module-level global) because it is async-safe and resets automatically when the async context ends, preventing bleed between concurrent requests:

```python
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")

def get_correlation_id() -> str:
    return _correlation_id.get()

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        cid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        _correlation_id.set(cid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = cid  # echoed back so clients can log it
        return response
```

Registered as the outermost middleware in `main.py` (before CORS), so it runs on every request including health checks:

```python
app.add_middleware(CorrelationIdMiddleware)
```

Every log call and every `ErrorDetail` response now carries `request_id=get_correlation_id()`, making it possible to filter a complete request trace with a single CloudWatch Logs Insights query.

**Sources:**
- [AWS Lambda Powertools Logger](https://docs.aws.amazon.com/powertools/python/latest/core/logger/)
- [Python contextvars](https://docs.python.org/3/library/contextvars.html)
- [Starlette BaseHTTPMiddleware](https://www.starlette.io/middleware/)

---

## 8. Security ✅

_Low-effort hardening that covers the most common scanner findings and prevents accidental info disclosure in production._

### 8a. Security response headers ✅

`app/middleware.py` — `SecurityHeadersMiddleware` appended to every response:

```python
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",   # prevents MIME-type sniffing
    "X-Frame-Options": "DENY",             # blocks clickjacking via iframes
    "Referrer-Policy": "no-referrer",      # avoids leaking API URLs in Referer
    "X-XSS-Protection": "1; mode=block",  # legacy filter for older browsers
}

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.update(_SECURITY_HEADERS)
        return response
```

`Strict-Transport-Security` is intentionally omitted — it belongs at the API Gateway / CloudFront layer. `Content-Security-Policy` belongs on the Next.js frontend (no HTML served from this API). Headers are set manually (not via a library) because there are only five static values with no variance per route.

Registered as the outermost middleware in `main.py` so it wraps every response including health checks:

```python
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CorrelationIdMiddleware)  # runs inside SecurityHeaders
```

### 8b. Disabling OpenAPI docs in production Lambda ✅

`app/main.py` — gated by `AWS_LAMBDA_FUNCTION_NAME` (same env var already used for CORS):

```python
_in_lambda = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

app = FastAPI(
    docs_url=None if _in_lambda else "/docs",
    redoc_url=None if _in_lambda else "/redoc",
    openapi_url=None if _in_lambda else "/openapi.json",
)
```

The TypeScript client is regenerated from a local dev server — the live Lambda endpoint does not need to expose the spec.

### 8c. Tightening CORS

_Pending — blocked on knowing the Vercel frontend domain. Both API Gateway (`infra/api.ts`) and the Function URL currently use `allowOrigins: ["*"]`. Once the domain is known, update both. Section 12 covers this alongside WAF._

### 8d. Agent prompt injection mitigations ✅

**Bedrock Guardrails** — optional, zero-code-path-change when no guardrail is configured:

`app/config.py`:
```python
GUARDRAIL_ID: str | None = os.environ.get("BEDROCK_GUARDRAIL_ID")
GUARDRAIL_VERSION: str = os.environ.get("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
```

`app/agent.py` — `**({...} if GUARDRAIL_ID else {})` is conditional keyword unpacking; avoids passing `None` to params that require real values:
```python
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
```

When `BEDROCK_GUARDRAIL_ID` is set (via SST env var at deploy time), every model invocation is evaluated by the guardrail before the response reaches the agent. `GUARDRAIL_VERSION` defaults to `"DRAFT"` so the latest saved version is used automatically during the authoring phase.

**Sources:**
- [Starlette BaseHTTPMiddleware](https://www.starlette.io/middleware/)
- [Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html)

---

## 9. Resilience ✅

_Bounds on how long and how hard the service will try before giving up._

### 9a. Agent stream timeout ✅

`app/config.py`:
```python
MAX_AGENT_SECONDS: int = 110  # 10s headroom before the 120s Lambda timeout
```

`app/api/routes/chat.py` — `asyncio.timeout` (Python 3.11+) wraps the entire stream iteration. When Bedrock hangs or retries exhaust time, `TimeoutError` is caught and converted to a structured SSE error event, then `done` is always emitted in `finally`:

```python
try:
    async with asyncio.timeout(MAX_AGENT_SECONDS):
        async for event in agent.stream_async(user_message):
            ...
except TimeoutError:
    logger.warning("Agent stream timed out", extra={"timeout_seconds": MAX_AGENT_SECONDS})
    metrics.add_metric(name="AgentError", unit=MetricUnit.Count, value=1)
    yield ServerSentEvent(data=json.dumps({"type": "error", "error": "Request timed out. Please try again."}))
finally:
    metrics.flush_metrics()
    yield ServerSentEvent(data=json.dumps({"type": "done"}))
```

The `finally` block guarantees `done` is always the last event — even on timeout or unhandled exception.

### 9b. Bedrock throttling and retry behaviour ✅

`app/agent.py` — boto3 retry mode set via environment variables at module load time. `setdefault` is used so an operator can override them in the SST environment without touching code:

```python
os.environ.setdefault("AWS_RETRY_MODE", "standard")  # exponential backoff
os.environ.setdefault("AWS_MAX_ATTEMPTS", "3")        # 1 initial + 2 retries
```

These are internal boto3 constants, not resource bindings — they belong in code, not SST's `environment` block (which is for cross-cutting Lambda config like `POWERTOOLS_SERVICE_NAME`).

**Why the timeout in 9a is still necessary even with retries:** retries multiply the potential wait time, they don't bound it. A 30-second Bedrock call with 3 attempts could run for 90+ seconds, blowing past the Lambda timeout and producing no `done` event.

**Sources:**
- [asyncio.timeout (Python 3.11)](https://docs.python.org/3/library/asyncio-task.html#asyncio.timeout)
- [boto3 retry configuration](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/retries.html)

---

## 10. Observability ✅

### 10a. Powertools Tracer (X-Ray)

`app/tracer.py` — shared singleton; auto-disables outside Lambda (no mocking required in tests):

```python
from aws_lambda_powertools import Tracer
tracer = Tracer()  # reads POWERTOOLS_SERVICE_NAME from env
```

`handler_bookings.py` — `@tracer.capture_lambda_handler` creates an X-Ray subsegment for the full invocation (see Section 7a for the full decorator stack).

`tools/bookings.py` — `@tracer.capture_method` wraps each tool function, creating subsegments for every DynamoDB call regardless of which Lambda invokes them:

```python
@tool
@tracer.capture_method
def get_booking_details(booking_id: str, restaurant_name: str) -> dict: ...

@tool
@tracer.capture_method
def create_booking(...) -> dict: ...

@tool
@tracer.capture_method
def delete_booking(booking_id: str, restaurant_name: str) -> str: ...
```

The Tracer patches boto3 automatically — every DynamoDB and Bedrock SDK call becomes a named X-Ray subsegment with latency and error metadata.

**LWA note:** `@tracer.capture_lambda_handler` only applies to `handler_bookings`. The chat Lambda runs under LWA+uvicorn — the Lambda runtime still creates a root X-Ray segment, and `@tracer.capture_method` on the tool functions creates subsegments within it. Powertools decorator on the handler itself is not reachable.

**X-Ray SDK maintenance mode (Feb 2026):** maintenance mode means no new features, but security and critical fixes continue. Powertools has OpenTelemetry/ADOT support on their p0 roadmap but has not shipped it yet. The current X-Ray surface area we use (`capture_lambda_handler`, `capture_method`) is stable. Revisit when Powertools ships their OTEL provider.

### 10b. Powertools Metrics (CloudWatch EMF)

`app/metrics.py` — shared singleton using Embedded Metric Format (emits via CloudWatch Logs — no `PutMetricData` API calls, no extra IAM permissions):

```python
from aws_lambda_powertools import Metrics
from aws_lambda_powertools.metrics import MetricUnit

metrics = Metrics(namespace="RestaurantBookingAgent")
```

**Bookings Lambda** — `@metrics.log_metrics(capture_cold_start_metric=True)` flushes the EMF blob at handler exit and emits a separate `ColdStart` metric automatically (see Section 7a).

**Chat Lambda** — `@metrics.log_metrics` never executes (LWA bypasses the handler). Manual flush in the generator's `finally` block is the only reliable flush point:

```python
# chat.py — stream_chat
metrics.add_metric(name="ChatRequest", unit=MetricUnit.Count, value=1)

# chat.py — generate_chat_events
if event.get("force_stop"):
    metrics.add_metric(name="AgentError", unit=MetricUnit.Count, value=1)

except Exception:
    metrics.add_metric(name="AgentError", unit=MetricUnit.Count, value=1)

finally:
    metrics.flush_metrics()  # manual flush — required for LWA path
    yield ServerSentEvent(data=json.dumps({"type": "done"}))
```

`tools/bookings.py` — business-level metric emitted on every successful booking:

```python
metrics.add_metric(name="BookingCreated", unit=MetricUnit.Count, value=1)
```

Metric summary:

| Metric | Source | When emitted |
|--------|--------|--------------|
| `ColdStart` | handler_bookings | First invocation of a new execution environment |
| `ChatRequest` | chat.py | Every POST /chat |
| `AgentError` | chat.py | force_stop or unhandled stream exception |
| `BookingCreated` | tools/bookings.py | Successful `create_booking` tool call |

**Sources:**
- [AWS Lambda Powertools Tracer](https://docs.aws.amazon.com/powertools/python/latest/core/tracer/)
- [AWS Lambda Powertools Metrics](https://docs.aws.amazon.com/powertools/python/latest/core/metrics/)
- [CloudWatch Embedded Metric Format](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format.html)
- [aws-xray-sdk-python maintenance mode](https://github.com/aws/aws-xray-sdk-python)

---

## 11. Health Check ✅

**Problem:** `GET /health → {"status": "ok"}` proved the Lambda was alive but not that DynamoDB was reachable. A broken table returned 200.

### 11a. Dependency health sub-checks ✅

`app/repositories/bookings.py` — added `ping()` using `describe_table` (no data read, no cost):

```python
def ping() -> None:
    """Lightweight DynamoDB reachability check — raises on any error."""
    _table.meta.client.describe_table(TableName=TABLE_NAME)
```

`app/main.py` — health endpoint extended with structured dependency check:

```python
_HEALTH_TIMEOUT = 2.0  # seconds per dependency probe

@app.get("/health", operation_id="healthCheck")
async def health() -> JSONResponse:
    dynamodb_status = "ok"
    try:
        await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, booking_repo.ping),
            timeout=_HEALTH_TIMEOUT,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning("Health check: DynamoDB unreachable")
        dynamodb_status = "error"

    overall = "ok" if dynamodb_status == "ok" else "degraded"
    status_code = 200 if overall == "ok" else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "dependencies": {"dynamodb": dynamodb_status},
            "not_checked": ["bedrock", "knowledge_base"],
        },
    )
```

### 11b. Timeouts on dependency checks ✅

`asyncio.wait_for(..., timeout=2.0)` wraps the synchronous `describe_table` call (run in a thread pool via `run_in_executor`). A slow or hung DynamoDB response returns a clean 503 rather than a Lambda-level 504.

### 11c. Why Bedrock and the Knowledge Base are omitted ✅

Bedrock has no lightweight probe — any call incurs a model invocation cost. The Knowledge Base retrieval API is similarly expensive. Both are deliberately listed in `not_checked`. Operators know exactly what "ok" covers.

**Tests:**
```python
def test_health_ok():
    with patch("app.repositories.bookings.ping"):
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["dependencies"]["dynamodb"] == "ok"

def test_health_degraded():
    with patch("app.repositories.bookings.ping", side_effect=Exception("unreachable")):
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
```

---

## 12. Rate Limiting and WAF ✅ (12a–12b) / pending (12c)

**What changed:** a new `infra/security.ts` module creates a single REGIONAL WAF WebACL and associates it with both entry points. Zero application code changes.

### 12a. WAF on the API Gateway ❌ (removed)

> **Correction:** `aws.wafv2.WebAclAssociation` does NOT support API Gateway HTTP API (v2) stages. WAF only supports REST API (v1) stage ARNs (`/restapis/{id}/stages/{stage}`). Attaching to an HTTP API ARN (`/apis/{id}/stages/$default`) fails at deploy time with `WAFInvalidParameterException`. The `ApiGatewayWafAssociation` resource was removed from `infra/security.ts`. WAF is attached only to the Function URL (Section 12b), which IS supported.

### 12a-removed. (was: WAF on the API Gateway)

`infra/security.ts` — `aws.wafv2.WebAcl` with two rules, associated with the API Gateway `$default` stage ARN via `api.nodes.stage.arn` (exported from `infra/api.ts`):

```typescript
// infra/security.ts
import { api, chatFunction } from "./api";

export const webAcl = new aws.wafv2.WebAcl("RestaurantWebAcl", {
  scope: "REGIONAL",
  defaultAction: { allow: {} },
  rules: [
    {
      name: "IPRateLimit",
      priority: 1,
      action: { block: {} },
      statement: {
        rateBasedStatement: { limit: 100, aggregateKeyType: "IP" },
      },
      visibilityConfig: { cloudwatchMetricsEnabled: true, metricName: "IPRateLimit", sampledRequestsEnabled: true },
    },
    {
      name: "AWSManagedRulesCommonRuleSet",
      priority: 2,
      overrideAction: { none: {} },
      statement: {
        managedRuleGroupStatement: {
          vendorName: "AWS",
          name: "AWSManagedRulesCommonRuleSet",
          // COUNT (not BLOCK): POST /chat accepts up to 50 × 4 096 chars — exceeds 8 KB default
          ruleActionOverrides: [{ name: "SizeRestrictions_BODY", actionToUse: { count: {} } }],
        },
      },
      visibilityConfig: { cloudwatchMetricsEnabled: true, metricName: "AWSManagedRulesCommonRuleSet", sampledRequestsEnabled: true },
    },
  ],
  visibilityConfig: { cloudwatchMetricsEnabled: true, metricName: "RestaurantWebAcl", sampledRequestsEnabled: true },
});

// SST's ApiGatewayV2 doesn't expose a stage node; construct the ARN manually
const apiStageArn = $interpolate`arn:aws:apigateway:${aws.getRegionOutput().name}::/apis/${api.nodes.api.id}/stages/$default`;
new aws.wafv2.WebAclAssociation("ApiGatewayWafAssociation", {
  resourceArn: apiStageArn,
  webAclArn: webAcl.arn,
});
```

Rate limit: 100 req per 5-minute window per IP (AWS minimum; ~1 req/3 s). A streaming Bedrock call takes 10–30 s, so legitimate users rarely approach this limit.

`SizeRestrictions_BODY` excluded from the Common Rule Set to prevent false positives on large (but valid) chat histories.

### 12b. WAF on the Chat Function URL ✅

Lambda Function URLs support WAF associations (GA since May 2023). The resource ARN is the function ARN with `/urls` appended:

```typescript
new aws.wafv2.WebAclAssociation("ChatFunctionWafAssociation", {
  resourceArn: $interpolate`${chatFunction.nodes.function.arn}/urls`,
  webAclArn: webAcl.arn,
});
```

Same WebACL shared with the API Gateway — simplifies rule management. Chat is inherently rate-limited by Bedrock latency; IP-based blocking is the primary cost-protection mechanism before the auth phase adds per-user limits.

`sst.config.ts` — import added after `api`:
```typescript
const api = await import("./infra/api");
await import("./infra/security");
const web = await import("./infra/web");
```

### 12c. CORS lockdown

_Pending — blocked on knowing the Vercel frontend domain. Both `api.ts` (API Gateway) and the Function URL `cors` config currently use `allowOrigins: ["*"]`. Once the domain is known, update both to the specific origin. WAF is already in place, so this is a one-line change per entry point._

---

## 13. Authorization

> **This is a separate phase with its own scope.** It requires user model decisions, frontend login UI, token refresh logic, and coordinated infra + backend + frontend changes. Stub only.

### 13a. Why this is its own phase

_Full auth requires: a Cognito User Pool (infra), a signup/login flow in the frontend, token refresh handling, and changes to the bookings routes to extract `user_id` from the JWT claim instead of accepting it from the client body. None of this can be done incrementally — it's an all-or-nothing change to the data model._

### 13b. Cognito User Pool + API Gateway JWT authorizer (bookings routes)

_SST creates the User Pool and an HTTP API JWT authorizer in a few lines. The authorizer validates tokens before the Lambda is invoked — rejected requests never reach FastAPI. No middleware needed for the bookings routes._

### 13c. JWT validation middleware for the chat Function URL

_The chat endpoint is a Function URL; API Gateway authorizers do not apply to it. The JWT must be validated in FastAPI. Add a `JWTAuthMiddleware` that reads the `Authorization: Bearer <token>` header, validates it against Cognito's JWKS endpoint, and injects the decoded claims into `request.state`. Unauthenticated requests receive an SSE `error` event and a `done` event before the stream starts._

### 13d. Extracting `user_id` from the token

_Once auth is live, `Booking.user_id` is no longer caller-supplied. Extract it from `request.state.claims["sub"]` in the chat route and in the bookings routes. Update the tool docstrings accordingly so the agent knows it doesn't need to ask the user for their ID._

---

## 14. Testing ✅

### 14a. Integration test strategy ✅

Two marker levels in `pyproject.toml`:

```toml
markers = [
    "integration: requires a deployed AWS test stage — INTEGRATION_TABLE_NAME / INTEGRATION_API_URL / INTEGRATION_CHAT_URL",
    "agent: requires real Bedrock credentials — run manually or nightly",
]
```

`tests/integration/conftest.py` — fixtures skip gracefully when env vars are absent:

```python
@pytest.fixture(scope="module")
def real_table():
    table_name = os.environ.get("INTEGRATION_TABLE_NAME")
    if not table_name:
        pytest.skip("INTEGRATION_TABLE_NAME not set")
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    real = dynamodb.Table(table_name)
    original = _repo_module._table
    _repo_module._table = real   # same swap pattern as moto unit fixture
    yield real
    _repo_module._table = original
```

`tests/integration/test_repositories.py` — real DynamoDB CRUD. Each test creates a unique item and deletes it in `finally` so it is safe to run repeatedly against a shared test-stage table. Tests: `create_get_roundtrip`, `create_with_special_requests`, `get_nonexistent_returns_none`, `delete_existing`, `delete_nonexistent_returns_false`, `delete_is_idempotent`.

Run:
```bash
INTEGRATION_TABLE_NAME=<name> uv run pytest tests/integration/test_repositories.py -v
```

### 14b. Testing the SSE stream end-to-end ✅

`tests/integration/test_api.py` — HTTP smoke tests against the real deployed test stage:

```python
def test_chat_stream_terminates_with_done(chat_url):
    payload = {"messages": [{"role": "user", "content": "Hi"}]}
    last_type = None
    with httpx.Client(timeout=60.0) as client:
        with client.stream("POST", f"{chat_url}/chat", json=payload) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if line.startswith("data:"):
                    raw = line[6:].strip()
                    if raw:
                        last_type = json.loads(raw).get("type")
    assert last_type == "done"
```

Also covers: health shape + security headers, oversized/missing messages → 422.

Run:
```bash
INTEGRATION_API_URL=https://... INTEGRATION_CHAT_URL=https://... \
  uv run pytest tests/integration/test_api.py -v
```

### 14c. Prompt regression testing ✅

`tests/integration/test_agent.py` — calls `agent.stream_async()` with real Bedrock. Tools are patched to return canned data (no real DynamoDB/KB needed); we test the LLM's routing decisions, not tool execution.

```python
async def test_restaurant_query_calls_retrieve():
    agent = Agent(model=model, tools=TOOLS, system_prompt=SYSTEM_PROMPT)
    mock_retrieve = MagicMock(return_value=_FAKE_RESTAURANTS)
    with patch("strands_tools.retrieve", mock_retrieve):
        events = [e async for e in agent.stream_async("What restaurants do you have?")]
    assert "retrieve" in _tool_names(events)

async def test_create_booking_not_called_without_confirmation():
    agent = Agent(model=model, tools=TOOLS, system_prompt=SYSTEM_PROMPT)
    events = [e async for e in agent.stream_async("Book a table for me tonight")]
    assert "create_booking" not in _tool_names(events)
```

Run manually or nightly — not on every push:
```bash
uv run pytest tests/integration/test_agent.py -v
```

---

## 15. CI/CD Pipeline ✅

Three workflow files under `.github/workflows/`. No manual `sst deploy` once these are in place.

### 15a. Pipeline overview ✅

Five stages across three workflows:

| Workflow | Trigger | Jobs |
|---|---|---|
| `ci.yml` | Every push + PRs to main | lint → unit-tests → sst-diff (PRs only) |
| `deploy.yml` | Merge to main | deploy-staging → smoke-test |
| `promote.yml` | Manual (`workflow_dispatch`) | deploy-production (gated by environment) |

`sst.config.ts` change — omit named AWS profile in CI so the pipeline uses `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` secrets directly:

```typescript
providers: {
  aws: {
    region: "us-east-1",
    ...(process.env.CI ? {} : { profile: "iamadmin-general" }),
  },
}
```

Also exports `ChatUrl` and `TableName` from the SST run() function so integration test env vars can be set from stack outputs after the first staging deploy.

### 15a-pre. Pre-commit hooks (prek) ✅

Developer-side quality gate that runs before every `git commit`. Uses [prek](https://github.com/j178/prek) — a Rust-native drop-in for pre-commit with no Python dependency.

`prek.toml` at repo root:

```toml
fail_fast = false
default_language_version = { python = "3.11" }

[[repos]]
repo = "https://github.com/astral-sh/ruff-pre-commit"
rev = "v0.15.2"
hooks = [
  { id = "ruff", args = ["--fix"], files = "^backend/" },
  { id = "ruff-format", files = "^backend/" },
]

[[repos]]
repo = "local"
hooks = [
  {
    id = "pylint", name = "pylint",
    entry = "backend/.venv/bin/pylint", language = "system",
    types = ["python"], files = "^backend/app/",
    args = ["--rcfile=backend/pyproject.toml"],
  },
]

[[repos]]
repo = "builtin"
hooks = [
  { id = "trailing-whitespace" },
  { id = "end-of-file-fixer" },
  { id = "check-yaml" }, { id = "check-toml" }, { id = "check-json" },
  { id = "detect-private-key" },
  { id = "no-commit-to-branch", args = ["--branch", "main"] },
]
```

pylint config in `backend/pyproject.toml` — globally disables rules that overlap with ruff or are false positives for this codebase:

```toml
[tool.pylint.messages_control]
disable = [
    "C0301",  # line-too-long — ruff handles
    "R0801",  # duplicate-code — false positive on similar Pydantic field lists
    "R0903",  # too-few-public-methods — Starlette middleware only needs dispatch()
]
```

Intentional complexity in `generate_chat_events` is suppressed inline (not globally):
```python
async def generate_chat_events(  # pylint: disable=too-many-branches,too-many-locals,too-many-statements
```

One-time developer setup:
```bash
uv tool install prek
prek install   # wires .git/hooks/pre-commit
```

### 15b. Lint and unit tests ✅

`ci.yml` — `lint` job runs `ruff check`, `ruff format --check`, and `pylint app/` from `working-directory: backend`. `unit-tests` job runs `pytest tests/unit/ -q`. Pipeline stops on failure — no deployment.

Key details:
- `astral-sh/setup-uv@v7` with `version: "0.10.8"` — pinned to avoid surprise breaks from uv releases
- `cache-dependency-glob: backend/uv.lock` — keys the cache on the lock file (more precise than `pyproject.toml`)
- `ruff check --output-format=github` — emits `::error file=...::` annotations; GitHub renders these as **inline comments on the PR diff** so violations appear on the offending line, not buried in the log

### 15c. The SST diff job ✅

`ci.yml` — `sst-diff` job runs only on pull requests (not direct pushes). Runs `npx sst diff --stage staging`, captures stdout, and posts/updates a PR comment titled `## SST Diff — staging`. Uses `continue-on-error: true` so the comment step always runs even if the stack doesn't exist yet (first deploy).

### 15d. Deploy to staging and smoke test ✅

`deploy.yml` — `deploy-staging` job runs `npx sst deploy --stage staging` on merge to `main`. `smoke-test` job follows with `curl --fail "$STAGING_API_URL/health" | jq .`. `STAGING_API_URL` is a GitHub Repository Variable set once after first deploy (Settings → Variables → Actions).

### 15e. Promote to production ✅

`promote.yml` — triggered by `workflow_dispatch`. Requires typing `"production"` in the confirmation input. Gates on the `production` GitHub Environment (configure required reviewers in Settings → Environments → production). Uses separate `PROD_AWS_*` secrets. The `protect: true` and `removal: "retain"` SST config are the last line of defence against accidental deletion.

**One-time setup checklist:**
1. Create IAM user (staging): `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` → GitHub Secrets
2. Create IAM user (production): `PROD_AWS_ACCESS_KEY_ID` + `PROD_AWS_SECRET_ACCESS_KEY` → GitHub Secrets
3. After first staging deploy: set `STAGING_API_URL` → GitHub Repository Variable
4. Optionally set `INTEGRATION_API_URL`, `INTEGRATION_CHAT_URL`, `INTEGRATION_TABLE_NAME` → GitHub Repository Variables (enables integration tests in CI)
5. Create `production` GitHub Environment with required reviewers

---

## Appendix: CloudWatch Quick Reference

```
# All errors in the last hour, with correlation ID
fields @timestamp, correlation_id, message
| filter level = "ERROR"
| sort @timestamp desc
| limit 50

# Error rate over time
fields @timestamp
| filter ispresent(metric_name) and metric_name in ["ChatRequests", "AgentErrors"]
| stats sum(metric_value) by metric_name, bin(5m)

# Cold start vs warm latency
fields @timestamp, cold_start, @duration
| stats avg(@duration) by cold_start
```

```bash
# Run unit tests only
cd backend && uv run pytest tests/unit/

# Run integration tests (requires test-stage env vars)
cd backend && uv run pytest tests/integration/ -m integration

# Tail live Lambda logs
aws logs tail /aws/lambda/<function-name> --follow --format short

# Local dev with SST resource stubs
SST_RESOURCE_Bookings='{"name":"test-table"}' \
SST_RESOURCE_RestaurantKB='{"id":"test-kb-id"}' \
uv run uvicorn app.main:app --port 8000
```
