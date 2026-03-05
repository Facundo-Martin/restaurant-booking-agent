# How to Build a Streaming FastAPI + Strands Agent Backend

> **Status: layout draft — sections are stubs pending agreement**

---

## 1. Introduction

_What we're building and why. The finished product in one paragraph. Link to the final repo._

---

## 2. Prerequisites

- Completed the [Strands Agents quickstart](#)
- `aws configure` done and Bedrock model access enabled for Claude 3.7 Sonnet
- SST deployed: the DynamoDB table and Bedrock Knowledge Base already exist
- `uv` installed
- Python 3.11+

---

## 3. Overview

_Big picture before any code:_

- What the backend is responsible for (what requests it handles, what AWS services it touches)
- Technology choices and the one-line reason for each (FastAPI, Strands Agents, DynamoDB, SSE, Mangum)
- A simple architecture diagram or annotated ASCII sketch
- The final file/folder structure we will end up with — so the reader can see the destination

---

## 4. Project Setup

_Everything needed to have a properly configured Python project. We do not write a single line of application logic in this section._

### 4a. Creating and managing a Python project with `uv`

_`uv init`, the `pyproject.toml` structure, adding dependencies, understanding the lock file. Why `uv` over pip/poetry._

### 4b. FastAPI production file/folder structure

_Two well-known structure approaches exist, and we pick one deliberately:_

**Approach A — domain-driven (zhanymkanov):** Each feature lives in its own package containing its own router, schemas, models, service, and exceptions. Scales well for large monoliths; every file you need for a feature is co-located. Reference: [fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices).

```
app/
├── auth/
│   ├── router.py
│   ├── schemas.py
│   ├── models.py
│   └── service.py
└── bookings/
    ├── router.py
    ├── schemas.py
    └── ...
```

**Approach B — flat/file-type-based:** All routers live in `api/routes/`, all schemas in `models/`, all repositories in `repositories/`. Lower cognitive overhead; easy to navigate for small teams. Pairs naturally with the repository pattern (see [this walkthrough](https://medium.com/@hadiyolworld007/the-fastapi-repo-pattern-and-folder-structure-you-actually-need-c5aa06c93436)). This roughly matches "option 2" from a [community discussion](https://www.reddit.com/r/FastAPI/comments/1nrne2s/fastapi_project_structure_advice_needed/) where the consensus is that approach A is overkill for smaller, simpler apps.

```
app/
├── api/routes/        # one file per router
├── models/            # Pydantic schemas
├── repositories/      # data access layer
├── tools/             # Strands @tool functions
├── agent.py
├── config.py
└── main.py
```

**We use Approach B.** This is a booking app with two resources (`bookings`, `chat`). Domain-driven organisation adds indirection without benefit at this scale. We do adopt the repository pattern from Approach B — routes and tools never touch boto3 directly.

_Create the skeleton now: the directories, empty `__init__.py` files, and empty module stubs. No logic yet._

### 4c. Tooling: linters and formatters

_Set up `ruff` for linting and formatting. Configure it in `pyproject.toml`. Run it once to verify._

### 4d. Pre-commit hooks

_What pre-commit is and why it matters. Install the `pre-commit` framework. Write a `.pre-commit-config.yaml` that runs `ruff` on every commit. First commit to verify the hook fires._

### 4e. Reading config from SST

_The problem: how does Lambda know the DynamoDB table name or Knowledge Base ID at runtime without hardcoding ARNs or making SSM calls? The SST link injection pattern. Write `config.py`. The local dev workaround (exporting `SST_RESOURCE_*` env vars)._

---

## 5. FastAPI Development

_Build a fully functional FastAPI application progressively. Everything in this section is testable in isolation — no Strands agent involved yet._

### 5a. Bootstrapping and running the application

_Write `main.py` and run it with `uvicorn`. Confirm we get a response. Introduce the app factory pattern._

### 5b. The health check endpoint

_Add `GET /health`. Why every production API needs one. Test it three ways: the auto-generated Swagger UI at `/docs`, `curl`, and a first unit test with `TestClient`._

### 5c. Data schemas with Pydantic

_Write `models/schemas.py`. Why schemas are defined before routes — they are the shared vocabulary for every layer. Walk through `Booking`, `ChatApiMessage`, `ChatApiRequest`._

### 5d. The repository layer

_Why a repository layer exists: routes and tools should never see raw DynamoDB dicts. Write `repositories/bookings.py`. The module-level `_table` client and the cold-start rationale. The composite key design. The three operations: `get`, `create`, `delete`. The `ConditionExpression` trick in `delete`._

### 5e. The bookings REST routes

_Add `GET /bookings/{id}` and `DELETE /bookings/{id}`. The one surprising design choice: why `restaurant_name` is a query parameter instead of a path segment (DynamoDB composite key). Wire up the router in `main.py`._

### 5f. Enabling CORS

_Why CORS is only needed in local dev. The `AWS_LAMBDA_FUNCTION_NAME` guard. Configure `CORSMiddleware` for `localhost:3000`._

### 5g. Unit testing

_Three testing sub-problems and how we solve each:_
- _Stubbing the SST `Resource` object before any app import (`sys.modules` injection in root `conftest.py`)_
- _Mocking DynamoDB with `moto` — the module-level `_table` swap fixture_
- _Route tests with `TestClient` — what to mock and what to leave real_

---

## 6. Strands Agents Development

_Build and validate the agent in complete isolation from FastAPI. By the end of this section the agent works end-to-end from a Python script or REPL — no HTTP involved._

### 6a. Creating a basic agent and running it locally

_Minimal Strands `Agent` with a `BedrockModel`. Run it in a script with a hardcoded question. Confirm Bedrock responds._

### 6b. The system prompt

_What a system prompt does in an agentic context. Write the restaurant assistant prompt. Guidance on writing effective system prompts (scope, tone, tool usage hints)._

### 6c. Module-level singletons: `BedrockModel` and `TOOLS`

_Move `BedrockModel` out of the script and into `agent.py` as a module-level singleton. Explain what state each object holds and why the model is safe to share across requests._

### 6d. Creating booking tools with `@tool`

_What the `@tool` decorator does: reads type annotations and the `Args:` docblock to generate the tool spec the LLM reads. Write `get_booking_details`, `create_booking`, `delete_booking`. Emphasise that the docstring is part of the API surface._

### 6e. The `KNOWLEDGE_BASE_ID` env var and the `retrieve` tool

_The `retrieve` tool from `strands-agents-tools` reads `KNOWLEDGE_BASE_ID` from the environment. Set it once at module load. Brief explanation of what RAG retrieval does for the agent._

### 6f. Running the agent end-to-end locally

_Wire all tools into the agent. Run a full conversation in a script: ask about a restaurant (triggers `retrieve`), then book a table (triggers `create_booking`). Verify DynamoDB gets the item._

### 6g. Testing the agent layer

_Unit-test the `@tool` functions by calling them directly (the decorator preserves the original signature). Mock the repository underneath. No agent object needed in these tests._

---

## 7. Integrating Strands into FastAPI

_Connect the agent to the HTTP layer. This section introduces SSE streaming — the most complex part of the backend._

### 7a. The per-request Agent — what changes and what doesn't

_Why `BedrockModel` and `TOOLS` stay as module-level singletons while `Agent` is created fresh per request. What `Agent` holds that makes it unsafe to share (conversation history). Cost of per-request creation: negligible._

### 7b. SSE primer — why not WebSockets

_What Server-Sent Events are, how `EventSource` works in the browser, why SSE is a better fit than WebSockets for a unidirectional LLM stream (stateless, works through API Gateway, no upgrade handshake)._

### 7c. The SSE event protocol

_Define the six event types our frontend expects: `text-delta`, `tool-call-start`, `tool-result`, `tool-error`, `error`, `done`. A table showing each event's shape._

### 7d. Implementing `POST /chat` with `sse-starlette`

_`EventSourceResponse`, `ServerSentEvent`, `X-Accel-Buffering`. The generator function pattern._

### 7e. Mapping Strands events to SSE events

_What `stream_async` yields. The three keys to watch for (`data`, `message`, `force_stop`). The two-phase tool lifecycle (role=assistant fires with full input before the tool runs; role=user fires with the result after). Why `current_tool_use` is the wrong hook._

### 7f. The `finally: done` guarantee

_Why `done` lives in the `finally` block rather than at the end of the `try`. What the frontend does if it never receives `done`._

### 7g. Testing the chat route

_How to test an SSE endpoint with `TestClient`. Mocking `agent.stream_async` to return a controlled async iterator. Asserting on the event sequence._

---

## 8. Moving to Production

_Everything needed to deploy the FastAPI app as an AWS Lambda function via SST._

### 8a. The Lambda entry point — Mangum

_What Mangum does in one sentence. Write `handler_chat.py`. The SST handler path convention (`backend/app/handler_chat.handler`). `lifespan="off"` and why it matters for Lambda._

### 8b. The catch-all root route

_Add the `GET / POST / … /` catch-all that returns a 404 with valid endpoints listed. Prevents confusing "502 bad gateway" errors when the client has the wrong URL._

### 8c. CORS revisited — production vs. local dev

_In Lambda, CORS is handled by API Gateway / Function URL config before the request reaches FastAPI. The `AWS_LAMBDA_FUNCTION_NAME` guard from section 5f means our middleware is correctly a no-op in production._

### 8d. CI/CD sketch

_A GitHub Actions pipeline outline: lint (ruff) → unit tests (pytest + moto) → `sst diff` → deploy staging → promote prod. Not implemented in full — pointers to the relevant SST and GHA docs._

---

## Appendix: Local Dev Quick Reference

_One copy-pasteable block: the `SST_RESOURCE_*` env vars needed to run `uvicorn` without a deployed stack._
