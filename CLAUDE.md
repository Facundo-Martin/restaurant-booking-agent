# CLAUDE.md — Restaurant Booking Agent

This file provides context and guidance for AI coding assistants working on this codebase.

---

## Project Overview

This project migrates the [Strands Agents restaurant assistant sample](https://github.com/strands-agents/samples/tree/main/02-samples/01-restaurant-assistant) from a Jupyter notebook POC into a production-ready, fully-deployed application on AWS.

The result is a polyglot monorepo containing:
- **SST v3** infrastructure (TypeScript / Pulumi)
- **Next.js** frontend (TypeScript)
- **FastAPI + Strands Agents** backend (Python)

All three are deployed as a single unit via SST.

---

## Current State

The repository is currently at the **starting scaffold** stage — the SST monorepo template has been initialized but not yet adapted for the restaurant agent. The target architecture and migration plan are documented in `claude-context/project.MD`. Implementation follows the phases described there.

Current structure (template defaults, not yet modified):
- `sst.config.ts` — SST entry point (generic template, not yet restaurant-specific)
- `infra/api.ts` / `infra/storage.ts` — placeholder infra (to be replaced)
- `packages/core/`, `packages/functions/`, `packages/scripts/` — SST template packages (to be replaced by `apps/web/` and `backend/`)
- `package.json` — uses **npm workspaces**; `claude-context/project.MD` recommends migrating to **pnpm workspaces**

---

## Target Architecture

Read `claude-context/project.MD` in full before making significant changes. Below is a condensed summary.

### AWS Services

| Service | Role |
|---|---|
| Amazon Bedrock | LLM inference (Claude 3.7 Sonnet) |
| Amazon Bedrock Knowledge Base | RAG over restaurant/menu docs |
| Amazon OpenSearch Serverless | Vector store backing the KB |
| Amazon S3 | Source `.docx` files for the KB |
| Amazon DynamoDB | Reservations table |
| AWS Lambda | Backend runtime (FastAPI via Mangum) |
| Amazon VPC | Private networking; replaces all `AllowFromPublic` access |

### Key Infrastructure Constraints

- **OSS namespace**: OpenSearch Serverless resources in Pulumi live under `aws.opensearch.Serverless*` — **not** `aws.opensearchserverless.*` and **not** `aws-native`. This is a common mistake; the correct namespace is `aws.opensearch.ServerlessCollection`, `aws.opensearch.ServerlessSecurityPolicy`, `aws.opensearch.ServerlessAccessPolicy`, etc.
- **OSS encryption policy must exist before the collection** — use `dependsOn` to enforce this.
- **OSS VPC endpoint vs. standard VPC endpoint** — OSS uses its own endpoint type (`aws.opensearch.ServerlessVpcEndpoint`), not `aws.ec2.VpcEndpoint`. Its ID is referenced in the network policy's `SourceVPCEs`.
- **`AllowFromPublic: false`** — the target network policy explicitly disables public access. Never re-enable it.
- **`aws-native` provider limitation** — `aws-native` does not support OSS data access policies. Use the classic `aws` provider throughout.

### SST Linking Pattern

SST's `link` system injects resource values at deploy time and grants IAM permissions automatically. Raw Pulumi resources (KB, OSS) must be registered with `sst.Linkable.wrap()` before they can be linked. Once linked, runtime code accesses values via `from sst import Resource` — no SSM calls, no hardcoded ARNs.

```python
# config.py
from sst import Resource
TABLE_NAME = Resource.Bookings.name
KB_ID      = Resource.RestaurantKB.id
```

---

## Target File Structure

```
restaurant-booking-agent/
│
├── CLAUDE.md
├── claude-context/                 # Architecture analysis and reference docs
│   ├── project.MD                  # Migration plan and SST snippets
│   ├── architecture.MD             # Design decisions and open issues
│   └── infrastructure.md           # Per-resource SST snippets with todo lists
├── sst.config.ts                   # SST entry point — imports infra modules
├── package.json                    # pnpm workspaces + Turborepo
├── pnpm-workspace.yaml             # apps/*, infra (backend excluded — managed by uv)
├── turbo.json
├── tsconfig.json
│
├── infra/                          # Infra split into logical modules
│   ├── networking.ts               # VPC + OSS VPC endpoint
│   ├── storage.ts                  # DynamoDB table + S3 bucket
│   ├── ai.ts                       # IAM role, OSS, KB, data source, Linkable.wrap()
│   ├── api.ts                      # Lambda function, link: [...]
│   └── web.ts                      # Next.js deployment
│
├── apps/
│   └── web/                        # Next.js frontend
│       ├── package.json
│       ├── next.config.ts
│       ├── app/                    # App Router
│       │   ├── layout.tsx
│       │   ├── page.tsx
│       │   └── globals.css
│       ├── components/
│       │   └── chat/
│       │       ├── ChatWindow.tsx
│       │       ├── MessageBubble.tsx
│       │       └── ChatInput.tsx
│       └── lib/
│           └── api.ts              # Generated typed client (do not hand-edit)
│
├── backend/                        # Python — FastAPI + Strands (uv-managed)
│   ├── pyproject.toml              # uv workspace config (required by SST Python bundler)
│   ├── app/
│   │   ├── handler.py              # Lambda entry point — wraps FastAPI with Mangum
│   │   ├── main.py                 # FastAPI app factory
│   │   ├── config.py               # from sst import Resource
│   │   ├── agent.py                # Strands Agent factory
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── chat.py         # POST /chat — SSE streaming
│   │   │       └── bookings.py     # GET/DELETE /bookings/:id
│   │   ├── tools/
│   │   │   └── bookings.py         # @tool functions + module-level boto3 client
│   │   └── models/
│   │       └── schemas.py          # Pydantic models
│   └── tests/
│       ├── unit/
│       └── integration/
│
└── kb-documents/                   # Source .docx files uploaded to S3 on deploy
    ├── Restaurant Directory.docx
    └── ...
```

---

## Technology Stack

### JavaScript / TypeScript
- **SST v3** — Pulumi-based IaC + deployment orchestration
- **pnpm workspaces** — JS/TS package management (target; currently npm)
- **Turborepo** — task pipeline caching (build, typecheck, lint)
- **Next.js (App Router)** — frontend
- **`@hey-api/openapi-ts`** — generates `apps/web/lib/api.ts` from FastAPI's OpenAPI spec; never hand-edit this file

### Python
- **uv workspaces** — Python dependency management (`backend/pyproject.toml`)
- **FastAPI** — HTTP API layer
- **Mangum** — wraps FastAPI for AWS Lambda
- **Strands Agents SDK** (`strands-agents`) — agent framework
- **Strands Agents Tools** (`strands-agents-tools`) — built-in tools (`retrieve`, `current_time`)
- **boto3** — AWS SDK (DynamoDB, Bedrock)
- **moto** — mock AWS services in unit tests

### AWS / Infrastructure
- **Pulumi `aws` provider** (classic) — all raw Pulumi resources; do not use `aws-native`
- **SST v3** — first-class components: `sst.aws.Dynamo`, `sst.aws.Bucket`, `sst.aws.Function`, `sst.aws.Nextjs`, `sst.aws.Vpc`

---

## Development Phases

Implement in order. Each phase is a prerequisite for the next.

### Phase 0 — Project Restructuring *(current focus)*
- Replace `packages/` SST template layout with `apps/web/` + `backend/`
- Migrate from npm workspaces to pnpm + Turborepo
- Add `pnpm-workspace.yaml`, `turbo.json`
- Restructure `infra/` into `networking.ts`, `storage.ts`, `ai.ts`, `api.ts`, `web.ts`
- Update `sst.config.ts` to use dynamic imports of all infra modules

### Phase 1 — Infrastructure as Code
- Implement all infra modules (see `claude-context/infrastructure.md` for per-resource SST snippets and open todos)
- VPC + OSS VPC endpoint in `infra/networking.ts`
- DynamoDB + S3 bucket in `infra/storage.ts`
- IAM role, OSS collection/policies, KB, data source, `sst.Linkable.wrap()` in `infra/ai.ts`
- Lambda function with `link: [table, kbBucket, knowledgeBase]` in `infra/api.ts`

### Phase 2 — Backend (FastAPI + Strands Agent)
- Implement `backend/` Python package
- `handler.py` + `main.py` + FastAPI routes
- `config.py` using `from sst import Resource` (zero SSM calls)
- `tools/bookings.py` with module-level boto3 client (initialized once per cold start)
- `agent.py` factory with all tools registered
- POST /chat route with SSE streaming

### Phase 3 — Frontend (Next.js)
- Implement `apps/web/` Next.js app
- Chat UI components
- Generate `lib/api.ts` client from FastAPI OpenAPI spec

### Phase 4 — Observability
- Structured JSON logging with correlation IDs
- AWS X-Ray tracing on Bedrock and DynamoDB calls
- CloudWatch metrics and alarms

### Phase 5 — Testing + CI/CD
- Unit tests with moto-mocked DynamoDB
- Prompt regression tests for agent behavior
- GitHub Actions pipeline: lint → test → `sst diff` → deploy staging → promote prod

---

## Key Patterns and Conventions

### Infra — module imports in `sst.config.ts`
Always use dynamic `await import(...)` for infra modules to ensure Pulumi resource ordering:
```typescript
async run() {
  const networking = await import("./infra/networking");
  const storage    = await import("./infra/storage");
  const ai         = await import("./infra/ai");
  const api        = await import("./infra/api");
  await import("./infra/web");
  return { ApiUrl: api.url, KbId: ai.knowledgeBaseId };
}
```

### Infra — Pulumi output resolution
Use `.apply()` for all Pulumi `Output<T>` values. `pulumi.interpolate` is equivalent for simple string interpolation. `$resolve()` unwraps SST-specific outputs before passing to `.apply()`.

### Infra — OSS resource ordering
```
ossEncryptionPolicy  ──dependsOn──►  ossCollection
ossCollection        ──dependsOn──►  knowledgeBase
kbExecutionRole      ──dependsOn──►  knowledgeBase
```

### Backend — boto3 initialization
Initialize boto3 clients at module level, not inside tool functions. This avoids re-initialization on every tool invocation:
```python
# Correct — initialized once per cold start
_table = boto3.resource("dynamodb").Table(TABLE_NAME)

@tool
def get_booking_details(booking_id: str, restaurant_name: str) -> dict:
    return _table.get_item(...)
```

### Backend — Lambda handler
```python
# backend/app/handler.py
from mangum import Mangum
from app.main import app

handler = Mangum(app)
```
The SST function handler path is `backend/app/handler.handler`.

### Backend — `retrieve` tool env var
The `retrieve` tool from `strands-agents-tools` reads `KNOWLEDGE_BASE_ID` from the environment. Set it once at module load in `agent.py`:
```python
import os
from app.config import KB_ID
os.environ["KNOWLEDGE_BASE_ID"] = KB_ID
```

### Frontend — generated client
`apps/web/lib/api.ts` is generated from FastAPI's OpenAPI spec via `@hey-api/openapi-ts`. Never hand-edit it. Regenerate with:
```bash
# From repo root
cd backend && uvicorn app.main:app & sleep 2 && \
  curl localhost:8000/openapi.json > ../apps/web/openapi.json && \
  cd ../apps/web && npx @hey-api/openapi-ts
```

---

## Common Mistakes to Avoid

| Mistake | Correct Approach |
|---|---|
| Using `aws.opensearchserverless.*` | Use `aws.opensearch.Serverless*` (classic provider) |
| Using `aws-native` for OSS | Use `aws` provider — `aws-native` lacks data access policy support |
| Setting `AllowFromPublic: true` on OSS | Use `AllowFromPublic: false` + `SourceVPCEs` with the OSS VPC endpoint ID |
| Creating the OSS collection before the encryption policy | Use `dependsOn: [ossEncryptionPolicy]` on the collection |
| Re-initializing boto3 inside tool functions | Initialize clients at module level |
| Making SSM calls at runtime | Use `from sst import Resource` — values are injected at deploy time |
| Hand-editing `apps/web/lib/api.ts` | Regenerate from OpenAPI spec |
| Amending commits | Create new commits; never use `--amend` unless explicitly asked |
| Force-pushing | Confirm with user before any force push |

---

## Environment and Tooling

- **Node.js** — managed by the SST toolchain; version pinned in `.nvmrc` if present
- **Python** — `>=3.11` (required by SST Python bundler); managed by `uv`
- **AWS credentials** — must be configured in the environment before running `sst dev` or `sst deploy`
- **SST stages** — use named stages (e.g., `sst deploy --stage staging`); production stage has `removal: "retain"` and `protect: true`

### Useful commands

```bash
# Start local dev environment (tunnels to live AWS resources)
npm run dev          # calls sst dev

# Deploy to a stage
npx sst deploy --stage staging

# View infrastructure diff before deploying
npx sst diff --stage staging

# Run Python tests
cd backend && uv run pytest

# Regenerate typed frontend API client
npm run generate:client
```

---

## Security Notes

- The original sample has `AllowFromPublic: true` on OSS — this is the primary security gap. Never reproduce it.
- IAM roles follow least-privilege: separate roles for KB ingestion vs. agent runtime.
- The DynamoDB table has no resource-based policy; access is controlled via the Lambda execution role (granted by SST's `link` mechanism).
- No secrets are stored in code or SSM Parameter Store — SST link injection is the sole mechanism for passing config to Lambda.
- Input sanitization relies on Pydantic models at the API boundary + the LLM system prompt. Do not trust tool inputs to be pre-validated.
