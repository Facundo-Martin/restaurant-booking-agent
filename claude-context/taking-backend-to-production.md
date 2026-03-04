# Taking the Backend Toward Production

> **Status: layout draft — sections are stubs pending implementation**

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

## 4. Fix Stale Tests

_Rewrite `tests/unit/test_api.py` to match the actual implementation. Nothing else in this guide is safe to implement until the test baseline is correct._

### 4a. Chat route tests

_The current chat route returns an `EventSourceResponse` (SSE stream), not a JSON body. FastAPI's `TestClient` supports SSE via the `stream=True` parameter on the request. Mock `agent.stream_async` (the function actually called in `chat.py`) to return a controlled `AsyncGenerator`. Assert on the sequence of parsed SSE events._

_Cover: a successful stream (yields `text-delta` then `done`), a tool cycle (yields `tool-call-start` then `tool-result` then `done`), a Bedrock exception (yields `error` then `done`), and a `force_stop` event._

### 4b. Verify existing tests still pass

_`test_repositories.py` and `tests/unit/tools/test_bookings.py` are correct — they test the repository and tool functions directly and use the moto fixture properly. Confirm they pass after the chat tests are rewritten._

---

## 5. Error Handling

_The current backend exposes `str(exc)` in SSE events and relies on FastAPI's default 422 shape for validation errors. This section standardizes all error surfaces before adding new features on top._

### 5a. A consistent error response model

_Define `ErrorResponse` in `models/schemas.py`: `{"error": {"code": str, "message": str, "request_id": str}}`. Every HTTP error and every SSE `error` event uses this shape — the frontend can unconditionally parse it._

_Add `AppException(HTTPException)` as the base class for all application-level errors. It carries a `code` string alongside the HTTP status (e.g., `"BOOKING_NOT_FOUND"`, `"AGENT_TIMEOUT"`). Routes raise `AppException` — never a bare `HTTPException`._

### 5b. Global exception handlers in `main.py`

_Register three handlers:_
- _`@app.exception_handler(AppException)` — maps the code and message to `ErrorResponse`, logs at `WARNING`._
- _`@app.exception_handler(RequestValidationError)` — maps Pydantic's 422 shape to `ErrorResponse`, HTTP 422._
- _`@app.exception_handler(Exception)` — logs the full traceback at `ERROR` with correlation ID; returns a generic `"An unexpected error occurred"` message to the client. **Never** expose `str(exc)` from an unhandled exception._

### 5c. SSE error events — sanitization

_Replace the `except Exception as exc: yield ServerSentEvent(... str(exc))` pattern in `chat.py`. The handler logs the full traceback and yields an `error` event containing only the correlation ID and a generic message. The ID lets the user report the failure; CloudWatch lets you find the full trace._

---

## 6. Input Validation Hardening

_Pydantic stops malformed requests. It doesn't stop expensive ones. This section adds constraints that prevent large payloads from reaching Bedrock unchecked._

### 6a. Payload limits on `/chat`

_Add `Field(max_length=4096)` to `ChatApiMessage.content`. Add a `model_validator` on `ChatApiRequest` that rejects more than `MAX_MESSAGES` items (e.g., 50). Both constants live in `config.py`._

_Add Starlette's body size middleware to reject requests above a byte limit before they reach Pydantic — avoids wasting Lambda memory on multi-megabyte JSON bodies._

### 6b. Stricter booking field constraints

_`Booking.date` is a plain `str` — callers can persist `"next tuesday"` in DynamoDB. Replace with a constrained ISO 8601 pattern. `party_size` becomes `Field(ge=1, le=20)`. `special_requests` gets `Field(max_length=500)`. These constraints propagate to the OpenAPI spec and the generated TypeScript client automatically._

---

## 7. Logging

_Replace the standard `logging.getLogger()` calls with Lambda Powertools Logger and add per-request correlation IDs. This is the foundation that makes everything in section 9 (observability) meaningful._

### 7a. Replacing `logging.getLogger` with Powertools Logger

_Add `aws-lambda-powertools` to `pyproject.toml`. Initialize `Logger(service="restaurant-booking")` at module level in each file that currently calls `logging.getLogger()`. The Logger emits JSON natively and auto-injects `cold_start`, `function_name`, `function_version`, and `xray_trace_id` on every record._

_Apply `@logger.inject_lambda_context` to the Mangum handlers (`handler_bookings.handler`). For the LWA-based chat handler, show the equivalent approach (Powertools middleware or manual context injection)._

_Local dev: when `AWS_LAMBDA_FUNCTION_NAME` is not set, Powertools still emits JSON — just without the Lambda-specific fields._

### 7b. Request correlation IDs

_A single `/chat` call triggers log statements across `chat.py`, `tools/bookings.py`, and `repositories/bookings.py` — but CloudWatch shows them as unrelated lines. The fix: generate a UUID per request and thread it through every log record for that request._

_Implement `CorrelationIdMiddleware` using Starlette's `BaseHTTPMiddleware`. Store the ID in a `contextvars.ContextVar` — not a module-level global — so it's safe across concurrent async calls and doesn't bleed between Lambda invocations that reuse the same execution environment. Inject the ID into Powertools Logger via `logger.append_keys(correlation_id=...)`. Return it to the client as `X-Request-ID`._

### 7c. Structured log events at agent lifecycle points

_The current codebase logs one line per request. A 12-second Bedrock call that invokes two tools should leave structured evidence at each step. Add `logger.info(...)` calls for: tool-call-start (tool name, input), tool-result (status, tool name). The `force_stop` warning already exists. Each call carries the correlation ID automatically via the `ContextVar`._

---

## 8. Security

_Low-effort hardening that covers the most common scanner findings and prevents accidental info disclosure in production._

### 8a. Security response headers

_Add `SecurityHeadersMiddleware` that sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and `X-XSS-Protection: 1; mode=block` on every response. `Strict-Transport-Security` is better set at API Gateway / CloudFront level — not here._

### 8b. Disabling OpenAPI docs in production Lambda

_`/docs` and `/openapi.json` are accessible to anyone with the Function URL. Gate them with the `AWS_LAMBDA_FUNCTION_NAME` check already used for CORS: pass `docs_url=None` and `openapi_url=None` to `FastAPI(...)` when running in Lambda. The TypeScript client is regenerated from a local dev server — the live endpoint doesn't need to expose the spec._

### 8c. Tightening CORS

_Both API Gateway (`infra/api.ts` line 8) and the Function URL (line 42) currently use `allowOrigins: ["*"]`. The infra TODO already calls this out. Once the Vercel frontend domain is known, restrict both to that origin. The FastAPI CORS middleware (local dev only) is already scoped to `localhost:3000` — no changes needed there._

### 8d. Agent prompt injection mitigations

_User input passes directly to `agent.stream_async` — a crafted message can attempt to override the system prompt. Document the mitigations in place (system prompt structure, tool docstrings as a separate authority). Introduce **Bedrock Guardrails** as the next layer: content filters evaluated before the model sees the input. Show how to attach a guardrail ID to `BedrockModel` in `agent.py`._

---

## 9. Resilience

_Bounds on how long and how hard the service will try before giving up._

### 9a. Agent stream timeout

_Wrap `agent.stream_async(user_message)` in `asyncio.wait_for(..., timeout=MAX_AGENT_SECONDS)` where `MAX_AGENT_SECONDS` lives in `config.py` (e.g., 110 seconds — leaving headroom before the 120-second Lambda timeout). When `asyncio.TimeoutError` fires, raise `AppException` with code `"AGENT_TIMEOUT"`, which the SSE error handler in section 5c converts to a structured error event before emitting `done`._

### 9b. Bedrock throttling and retry behaviour

_`BedrockModel` delegates to boto3, which applies `standard` retry mode with exponential backoff by default. Show how to verify this is in effect and set `max_attempts` explicitly if needed. Explain why the agent-level timeout in 9a is still necessary even with retries: retries multiply the potential wait time, they don't bound it._

---

## 10. Observability

_CloudWatch + X-Ray via Lambda Powertools Tracer and Metrics. Zero additional infrastructure._

### 10a. Powertools Tracer (X-Ray)

_Enable active tracing on both Lambda functions in `infra/api.ts` (`tracing: "active"`). Initialize `Tracer(service="restaurant-booking")` at module level in relevant files. Add `@tracer.capture_method` to repository functions and the `@tool` functions in `tools/bookings.py`. The Tracer patches boto3 automatically — every DynamoDB and Bedrock call becomes an X-Ray sub-segment._

_Note: the chat function uses LWA + Function URL. Active tracing on the SST function config covers the Lambda invocation; boto3 patch covers DynamoDB and Bedrock sub-segments within it._

_Show the resulting X-Ray service map: Lambda → DynamoDB for bookings, Lambda → Bedrock Runtime for chat. Show how to read the trace waterfall to identify slow tool calls._

### 10b. Powertools Metrics

_Define two CloudWatch custom metrics: `ChatRequests` (count per invocation) and `AgentErrors` (count, incremented when the SSE `error` event fires). Metrics are flushed automatically when the Lambda handler exits._

_Show a CloudWatch Logs Insights query that plots error rate over time. This is the first operational alert surface the service has._

---

## 11. Health Check

_`GET /health → {"status": "ok"}` proves the Lambda is alive. It does not prove DynamoDB is reachable._

### 11a. Dependency health sub-checks

_Extend the health endpoint to probe DynamoDB with a lightweight `describe_table` call. Shape: `{"status": "ok" | "degraded", "dependencies": {"dynamodb": "ok" | "error"}, "not_checked": ["bedrock", "knowledge_base"]}`. Return HTTP 200 when all dependencies are healthy, HTTP 503 otherwise. Reuse the boto3 client from `repositories/bookings.py` — no new client needed._

### 11b. Timeouts on dependency checks

_Each sub-check runs inside `asyncio.wait_for(..., timeout=2.0)`. A slow DynamoDB response should not cause the health check to time out at the Lambda level, leaving the uptime monitor with an unstructured 504._

### 11c. Why Bedrock and the Knowledge Base are omitted

_Bedrock has no lightweight probe — any call incurs a model invocation cost. The Knowledge Base retrieval API is similarly expensive. Both are deliberately listed in `not_checked`. Operators know exactly what "ok" covers._

---

## 12. Rate Limiting and WAF

_AWS WAF web ACL attached to both entry points. Zero application code. This is an infra change in `infra/api.ts`._

### 12a. WAF on the API Gateway

_Create an `aws.wafv2.WebAcl` in a new `infra/security.ts` module. Attach it to the `RestaurantApi`. Configure a rate-based rule (e.g., 100 requests per 5-minute window per IP) and enable the AWS Managed Rules Common Rule Set (covers OWASP Top 10 patterns). The `infra/api.ts` TODO already calls this out._

### 12b. WAF on the Chat Function URL

_Lambda Function URLs have supported WAF associations since 2023 via `aws.lambda.FunctionUrlConfig` / `aws.wafv2.WebAclAssociation`. Associate the same (or a separate, more permissive) web ACL to `chatFunction.url`. A streaming Bedrock call is inherently expensive — IP-based rate limiting here is the primary cost-protection mechanism before the auth phase adds per-user limits._

### 12c. CORS lockdown (same file)

_Update `allowOrigins` on both the API Gateway and the Function URL from `["*"]` to the Vercel frontend domain. This is the right moment since WAF and CORS are both in `infra/api.ts` / `infra/security.ts`._

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

## 14. Testing

_Fix the stale tests first (section 4), then add integration tests._

### 14a. Integration test strategy

_Two levels: (1) moto-mocked DynamoDB — already in place, fast; (2) real DynamoDB in a `test` SST stage — proves the repository layer works end-to-end. The `test` stage is cheap: no OSS, no Knowledge Base, just Lambda + DynamoDB._

_Mark integration tests with `@pytest.mark.integration` to exclude them from the default `pytest` run._

### 14b. Testing the SSE stream end-to-end

_`httpx`'s async client can consume SSE streams. In unit tests, mock `agent.stream_async` to return a controlled `AsyncGenerator` and assert on the SSE event sequence. In integration tests against the `test` stage, hit the real endpoint with a simple question and assert the stream terminates with `done`._

### 14c. Prompt regression testing

_The agent's behaviour is defined by the system prompt and tool docstrings. A model version bump or prompt edit can silently change it. Write a small set of fixed dialogues that assert on the SSE event sequence (e.g., `tool-call-start` with `toolName == "create_booking"` must not appear before a confirmation exchange). Run these against `agent.stream_async` directly — no HTTP layer involved. Mark `@pytest.mark.agent` and run them manually or in a nightly CI job, not on every push._

---

## 15. CI/CD Pipeline

_A GitHub Actions pipeline that enforces quality gates before every deployment. No manual `sst deploy` once this is in place._

### 15a. Pipeline overview

_Five stages in order: **lint** → **unit tests** → **sst diff** → **deploy staging** → **promote prod**. The diff stage surfaces infra changes before they apply. Production promotion is a separate, manually triggered job._

### 15b. Lint and unit tests

_`uv run ruff check .` and `uv run pytest tests/unit/`. Run on every push and every PR. Cache the uv venv keyed on `pyproject.toml` hash. Pipeline stops on failure — no deployment._

### 15c. The SST diff job

_`npx sst diff --stage staging` runs after tests pass. Post the diff as a PR comment. Block merge if the diff touches a retained resource (DynamoDB table, OSS collection) without an explicit `[allow-destroy]` label._

### 15d. Deploy to staging and smoke test

_`npx sst deploy --stage staging` on merge to `main`. Follow with `curl -f $STAGING_URL/health` — pipeline fails if the health check returns non-200._

### 15e. Promote to production

_Triggered by a GitHub release tag or manual `workflow_dispatch`. Targets `--stage prod`. The `protect: true` and `removal: "retain"` SST config are the last line of defence against accidental deletion._

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
