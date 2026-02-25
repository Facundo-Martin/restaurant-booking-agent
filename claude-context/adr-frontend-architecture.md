# ADR: Frontend Architecture Decision

**Date:** 2026-02-25
**Status:** Accepted
**Branch:** feat/frontend-chat-ui

---

## Context

Before building the frontend, we evaluated whether to adopt the T3 stack
(Next.js + tRPC + Drizzle + RDS Postgres) given the developer's strong
familiarity with it, or to stay with the simpler planned architecture
(Next.js + fetch-based typed API client + existing DynamoDB).

The SST docs show a working T3-on-AWS example using `sst.aws.Postgres` +
`sst.aws.Nextjs` linked through the SST resource system, which is a clean
and well-supported pattern.

---

## The Core Problem: Language Split

The Strands agent is Python. tRPC is TypeScript. They cannot share a
process. Adopting T3 does not eliminate the Python FastAPI service — it adds
a second backend alongside it.

The resulting architecture would be:

```
Browser
  ├── tRPC (TypeScript) ──► Drizzle ──► RDS Postgres  [bookings CRUD]
  └── fetch             ──► Python FastAPI ──► Strands  [chat/agent]
```

This creates an immediate data consistency problem: the Python agent tools
(`create_booking`, `delete_booking`) also write bookings. They would either
need to target a different database (two sources of truth) or be migrated to
Postgres (requiring `asyncpg`/`psycopg3`, VPC connectivity, and RDS Proxy
support in the Python service).

Neither option is acceptable at this stage:
- Two databases → bookings can diverge between the agent and the UI
- One Postgres → Python code needs significant rework and new infrastructure
  connectivity that is currently not implemented

tRPC's primary value — end-to-end type safety across the full request path —
is also undermined when the most important endpoint (`POST /chat`) is
excluded from it and remains a plain REST call.

---

## Cost Analysis

Adopting T3 would require the following always-on AWS infrastructure:

| Resource              | Monthly cost | Reason required             |
|-----------------------|--------------|-----------------------------|
| VPC NAT gateway       | ~$35         | Lambda/RDS internet access  |
| RDS t4g.micro         | ~$15         | Minimum viable Postgres      |
| RDS Proxy             | ~$15         | Serverless connection pooling|
| Bastion host (EC2)    | ~$5          | Local dev tunnel to RDS     |
| **Total**             | **~$70/mo**  |                             |

The current DynamoDB table costs effectively zero at this traffic level.
The data model is a single table with 6 fields — there are no relational
queries, no joins, no schema migrations. DynamoDB is not a limitation here.

---

## Decision

**Keep the current architecture. Do not adopt T3 for this project.**

Frontend stack:
- **Next.js 15** (App Router)
- **Typed API client** in `apps/web/lib/api.ts` — generated from FastAPI's
  OpenAPI spec via `@hey-api/openapi-ts`
- **No tRPC** — there is no TypeScript backend to attach it to
- **No Drizzle, no RDS** — DynamoDB is already deployed, working, and
  appropriate for the data model

The Python FastAPI service remains the single backend for all operations:
agent chat, bookings CRUD, and the health check.

---

## When to Revisit

T3 becomes the right choice if the project evolves to include:

- **Multi-tenant data** — restaurants as managed entities with their own
  users, menus, and availability windows
- **Relational queries** — joins across users, restaurants, time slots,
  reservations
- **A TypeScript agent layer** — if Strands/Python is replaced by a
  TypeScript agent framework, tRPC could cover the full request path
- **User authentication** — a user model with sessions, roles, and
  per-user booking history benefits from Postgres and Drizzle relations

At that point the architecture conversation should be reopened from scratch,
and the Python/TypeScript split should be reconsidered holistically rather
than layered on top of the current design.

---

## Frontend Implementation Plan

### Tooling and runtime

**Bun** — package manager and script runner for `apps/web`. Faster
installs and script execution than Node/npm. Used exclusively inside
`apps/web`; the monorepo root continues to use pnpm (enforced via
`only-allow pnpm`). The root check only fires on root-level installs so
the two coexist without conflict. Turbo invokes `apps/web` scripts via
the `package.json` definitions, which Bun executes.

**t3-env (`@t3-oss/env-nextjs`)** — Zod-validated environment variables.
Defines a typed `env` object imported throughout the app instead of raw
`process.env`. Throws at build time on missing or malformed vars rather
than silently passing `undefined` to the API client.

```ts
// apps/web/env.ts
import { createEnv } from "@t3-oss/env-nextjs";
import { z } from "zod";

export const env = createEnv({
  client: {
    NEXT_PUBLIC_API_URL: z.string().url(),
  },
  runtimeEnv: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
});
```

**Tailwind CSS** — required for Vercel AI Elements (components are
Tailwind-styled). Verify peer dependency requirements on install.

**ESLint (`eslint-config-next`)** — Next.js built-in config. Already
included in the root Turbo `lint` pipeline.

**`@/*` path alias** — configured in `tsconfig.json`, avoids deep
relative import chains.

**Explicitly excluded:**
- Prettier — ESLint handles formatting-adjacent rules sufficiently
- Husky / lint-staged — deferred to Phase 5 (CI/CD)
- TanStack Query — bookings are simple one-shot fetches; caching layer
  not warranted at this scale

### Library choices

**Vercel AI Elements** (`elements.ai-sdk.dev`) — pre-built React
components for AI chat UIs (message list, bubbles, input). These are
pure UI primitives with no AI SDK dependency and no vendor lock-in.
They are used solely for the chat interface appearance.

**Vercel AI SDK is explicitly excluded.** Reasons:
- `useChat` manages message history in component state only — no
  cross-session or cross-user memory
- Real memory requires backend integration (AgentCore, mem0, or Strands
  memory) which the AI SDK cannot provide and actively conflicts with
- The streaming wire format expected by `useChat` would require
  re-shaping the Python backend to match Vercel's protocol
- Vendor lock-in with no meaningful benefit given our Python agent layer

**hey-api (`@hey-api/openapi-ts`)** — generates a typed TypeScript
client from FastAPI's `/openapi.json`. Provides type-safe request params
and response shapes for the bookings endpoints. Not used for the chat
endpoint (managed separately via plain fetch + local state).

**Memory** is a backend concern deferred to a later phase. Candidates:
AWS Bedrock AgentCore Memory, mem0, or Strands' built-in memory. The
frontend is deliberately stateless between sessions.

### Responsibility split

| Concern | Handled by |
|---|---|
| Chat UI components | Vercel AI Elements |
| Typed HTTP client | hey-api (generated from OpenAPI) |
| In-session message state | Local React state (`useState`) |
| Multi-session memory | Future: AgentCore / mem0 (backend) |
| Agent logic, tool calls | Strands + Python FastAPI |

### Target structure

```
apps/web/
├── package.json
├── tsconfig.json
├── next.config.ts
├── app/
│   ├── layout.tsx        # Root layout, metadata
│   ├── page.tsx          # Renders <ChatWindow />
│   └── globals.css       # Global reset + CSS variables
├── components/
│   └── chat/
│       ├── ChatWindow.tsx      # Owns message state, calls API
│       ├── MessageBubble.tsx   # Single message (user | assistant)
│       └── ChatInput.tsx       # Textarea + send button
└── lib/
    └── api.ts            # Typed client — generate from OpenAPI spec
```

### API client

`lib/api.ts` is generated by hey-api from FastAPI's OpenAPI spec. It
covers `GET /bookings/{id}` and `DELETE /bookings/{id}`. The base URL is
read from `NEXT_PUBLIC_API_URL` (set in Vercel environment settings to
the API Gateway URL output by SST). For local dev it falls back to
`http://localhost:8000`.

The `POST /chat` endpoint is called via a plain `fetch` in
`ChatWindow.tsx` — not through the generated client — because in-session
message history is managed as local React state alongside the call.

Regenerate after any backend schema change:
```bash
cd backend && uv run uvicorn app.main:app &
curl localhost:8000/openapi.json > ../apps/web/openapi.json
cd ../apps/web && npx @hey-api/openapi-ts
```

### Chat UX behaviour

- Agent response is a full JSON payload (not streaming) — display when
  the promise resolves
- Show a loading indicator while the request is in flight (Bedrock
  responses take 2–10s)
- `Enter` submits, `Shift+Enter` inserts a newline
- Input is disabled while a request is in flight to prevent the
  concurrency error on the singleton agent

### Deployment

Deployed to **Vercel** independently from the SST stack (not via
`sst.aws.Nextjs`). Set `NEXT_PUBLIC_API_URL` to the API Gateway URL in
Vercel's environment settings. CORS on the API Gateway is already
configured to `allowOrigins: ["*"]` with a TODO to tighten it to the
Vercel domain once known.
