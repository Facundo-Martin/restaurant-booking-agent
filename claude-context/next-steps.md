# Next Steps — Restaurant Booking Agent

## Current state summary

| Area | Status |
|---|---|
| `infra/networking.ts` | ✅ Deployed — VPC + bastion |
| `infra/storage.ts` | ✅ Deployed — Aurora + DynamoDB + S3 |
| `infra/ai.ts` | ✅ Deployed — KB + ingestion pipeline |
| `infra/api.ts` | ⚠️ Declared but not wired — routes exist, handler files don't |
| `backend/` | ❌ Does not exist |
| `apps/web/` | ❌ Does not exist |
| Monorepo structure | ⚠️ Still SST template defaults (`packages/`) — needs cleanup |

### `infra/api.ts` — what "partially built" means

The API Gateway and Lambda *configurations* exist (routes, timeouts, memory, permissions) — but the Python handler files they reference don't exist yet:

```typescript
handler: "backend/app/handler_chat.handler",     // ← file doesn't exist
handler: "backend/app/handler_bookings.handler",  // ← file doesn't exist
```

The `link: [table, knowledgeBase]` lines are also commented out because there is nothing to link to yet. `infra/api.ts` is a declaration waiting for an implementation.

---

## Build order

```
1. Monorepo restructure   ~20 min   clean up template, wire pnpm + Turborepo
2. Backend                           the core of the application
   2a. Project scaffold              pyproject.toml, folder structure
   2b. Config + tools                SST Resource bindings, DynamoDB tools
   2c. Agent                         Strands agent factory
   2d. FastAPI routes                /chat, /bookings
   2e. Lambda handlers               Mangum wrapper
   2f. Wire infra/api.ts             uncomment links, deploy, test with curl
3. Frontend                          Next.js chat UI on Vercel
```

The frontend has nothing to call until the backend exists — build backend first.

---

## Step 1 — Monorepo restructure

### What to do

- Delete `packages/core`, `packages/functions`, `packages/scripts` (SST template boilerplate — not needed for this project)
- Add `pnpm-workspace.yaml` declaring `apps/*` as workspaces
- Add `turbo.json` for build/typecheck/lint task caching
- Migrate `package.json` from npm workspaces to pnpm

### Why pnpm over npm

Strict dependency isolation — packages can only import things they have explicitly declared, no accidental phantom imports from hoisted `node_modules`. Significantly faster installs and the de facto standard for JS monorepos in 2025.

### Why Turborepo

One thing: task caching. `turbo run build` knows which packages changed and skips rebuilding the rest. Modest benefit now, earns its keep as the project grows.

### Key rule: `backend/` is excluded from the pnpm workspace

Python is managed by `uv`, not pnpm. Mixing them would be confusing. The two sides are only linked at deploy time through SST.

### Target config files

**`pnpm-workspace.yaml`**
```yaml
packages:
  - "apps/*"   # picks up apps/web and any future apps
  # backend intentionally omitted — Python managed by uv, not pnpm
```

**`turbo.json`**
```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": { "dependsOn": ["^build"], "outputs": [".next/**", "!.next/cache/**"] },
    "typecheck": { "dependsOn": ["^build"] },
    "lint": {},
    "dev": { "cache": false, "persistent": true }
  }
}
```

---

## Step 2 — Backend

### What `uv` is

`uv` is the modern Python package manager — the equivalent of `npm`/`pnpm` for Python. It replaces `pip`, `pip-tools`, `virtualenv`, and `pyenv` for this project. The key file is `pyproject.toml` — the Python equivalent of `package.json`.

SST's Python bundler specifically requires `uv` with a `pyproject.toml` at the `backend/` root. When `sst deploy` runs, SST calls `uv` to resolve dependencies, creates a virtualenv, and zips the result for Lambda. You never manually manage the Lambda deployment package.

### How SST resolves handler paths

In `infra/api.ts`:
```
"backend/app/handler_chat.handler"
```
SST reads this as: in the `backend/` directory, find `app/handler_chat.py`, call the `handler` function inside it. The first segment (`backend/`) is where SST looks for `pyproject.toml` for bundling. Everything after is a Python module path.

### Target folder structure

```
backend/
├── pyproject.toml          # uv workspace — declares all Python dependencies
└── app/
    ├── handler_chat.py     # Lambda entry point for /chat
    ├── handler_bookings.py # Lambda entry point for /bookings
    ├── main.py             # FastAPI app factory
    ├── config.py           # from sst import Resource — single source of truth for config
    ├── agent.py            # Strands Agent factory, cached at module level
    ├── api/
    │   └── routes/
    │       ├── chat.py     # POST /chat logic
    │       └── bookings.py # GET/DELETE /bookings logic
    ├── tools/
    │   └── bookings.py     # @tool functions + module-level boto3 client
    └── models/
        └── schemas.py      # Pydantic request/response models
```

### Why two handler files

SST needs the handler path at the *function* level. If both Lambda functions pointed to the same `handler.py`, both would load the entire app including Strands and Bedrock dependencies — the bookings function would pay the cold-start penalty of an LLM workload it doesn't need. Separate entry points keep each function minimal.

### What each file does

**`pyproject.toml`** — declares Python dependencies. Key ones:
- `fastapi` — web framework
- `mangum` — Lambda ↔ ASGI adapter
- `strands-agents` — agent framework
- `strands-agents-tools` — built-in tools (`retrieve`, `current_time`)
- `boto3` — AWS SDK (DynamoDB)
- `sst` — SST Python SDK for `Resource` bindings (installed from SST's git repo)

**`config.py`** — reads SST-injected values once at module load. No SSM calls, no hardcoded ARNs:
```python
from sst import Resource

TABLE_NAME = Resource.Bookings.name
KB_ID      = Resource.RestaurantKB.id
```

**`tools/bookings.py`** — the three DynamoDB tools. The boto3 client is initialized *once at module level* so it is reused across every warm invocation (Lambda performance pattern):
```python
_table = boto3.resource("dynamodb").Table(TABLE_NAME)

@tool
def get_booking_details(booking_id: str, restaurant_name: str) -> dict: ...

@tool
def create_booking(...) -> ...: ...

@tool
def delete_booking(booking_id: str, restaurant_name: str) -> str: ...
```

**`agent.py`** — creates the Strands agent with all tools, also cached at module level. Sets `KNOWLEDGE_BASE_ID` in the environment so the `retrieve` tool from `strands-agents-tools` picks it up:
```python
import os
from app.config import KB_ID
os.environ["KNOWLEDGE_BASE_ID"] = KB_ID

_agent = create_agent()  # cached — one cold start cost, reused on warm invocations
```

**`main.py`** — standard FastAPI app factory. Mounts routers. Can also be run locally with `uvicorn app.main:app` for development without Lambda.

**`handler_chat.py` / `handler_bookings.py`** — Mangum wrapper. Mangum translates the Lambda event/context format into an ASGI request that FastAPI understands, and translates the FastAPI response back to a Lambda response:
```python
from mangum import Mangum
from app.main import app
handler = Mangum(app)
```

### Open design question: streaming

Mangum buffers the full response body before returning it — FastAPI's `StreamingResponse` will not stream token by token to the client. For the POC, the simplest path is returning the complete agent response as a single JSON body. Lambda Response Streaming is possible but adds complexity. Decide before writing the `/chat` route.

### Wrapping up: wire `infra/api.ts`

Once handler files exist, uncomment the `link:` arrays in `infra/api.ts`, deploy, and test with `curl`. This is the integration checkpoint before touching the frontend.

---

## Step 3 — Frontend

### Approach

- **Next.js** in `apps/web/` with the App Router
- **Deployed to AWS via `sst.aws.Nextjs`** — stays inside `sst deploy`, no separate dashboard
- SST provisions CloudFront (CDN) + S3 (static assets) + Lambda (SSR) automatically
- `NEXT_PUBLIC_API_URL` is injected at deploy time by SST — no manual env var management

**`infra/web.ts`**
```typescript
import { url } from "./api";

new sst.aws.Nextjs("Web", {
  path: "apps/web",
  environment: {
    NEXT_PUBLIC_API_URL: url,
  },
});
```

Then add `await import("./infra/web")` to `sst.config.ts`.

### Components

```
apps/web/
└── app/
│   ├── layout.tsx
│   ├── page.tsx          # chat page
│   └── globals.css
└── components/
│   └── chat/
│       ├── ChatWindow.tsx    # message history, manages request lifecycle
│       ├── MessageBubble.tsx # renders a single user/assistant message
│       └── ChatInput.tsx     # input bar + send button
└── lib/
    └── api.ts            # generated typed client — do not hand-edit
```

### Typed API client

Generate a TypeScript client from FastAPI's OpenAPI spec — never hand-write fetch calls:

```bash
# Run FastAPI locally, export the spec, generate the client
cd backend && uvicorn app.main:app &
sleep 2
curl localhost:8000/openapi.json > ../apps/web/openapi.json
cd ../apps/web && npx @hey-api/openapi-ts
```

Add this as a root script (`generate:client`) so it can be re-run whenever the API changes.

### Cost note

`sst.aws.Nextjs` at low traffic costs ~$1–2/month (CloudFront + Lambda for SSR). At zero traffic it is effectively free. The tradeoff vs Vercel is no automatic preview URLs per PR — these can be added with `sst deploy --stage pr-{number}` in GitHub Actions if needed later.

---

## Decision log

| Decision | Choice | Reason |
|---|---|---|
| Python package manager | `uv` | Required by SST Python bundler; modern, fast |
| Web framework | FastAPI | Auto-generates OpenAPI spec; Pydantic validation; async-native |
| Lambda adapter | Mangum | Standard ASGI↔Lambda bridge |
| Streaming | Deferred — single JSON response for POC | Mangum buffers full response; streaming needs extra work |
| Frontend hosting | `sst.aws.Nextjs` on AWS | Stays inside `sst deploy`; SST injects API URL automatically; ~$1–2/month at low traffic |
| Frontend client | Generated via `@hey-api/openapi-ts` | Type-safe, always in sync with backend schema |
| Monorepo JS tooling | pnpm + Turborepo | Industry standard for polyglot monorepos in 2025 |
