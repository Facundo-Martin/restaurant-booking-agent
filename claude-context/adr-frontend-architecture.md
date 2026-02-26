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

**Tailwind CSS** — required by the shadcn/ui component set. All
components are Tailwind-styled; CSS variables drive the OKLCH theme.

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

**Custom shadcn/ui components (from v0 prototype)** — a complete,
purpose-built chat UI already exists at
`github.com/Facundo-Martin/v0-restaurant-assistant-ui`. It was built
with shadcn/ui + Tailwind CSS and is ready to migrate directly into
`apps/web/`. Vercel AI Elements are not needed.

**Vercel AI SDK is explicitly excluded.** Reasons:
- `useChat` manages message history in component state only — no
  cross-session or cross-user memory
- Real memory requires backend integration (AgentCore, mem0, or Strands
  memory) which the AI SDK cannot provide and actively conflicts with
- The streaming wire format expected by `useChat` would require
  re-shaping the Python backend to match Vercel's protocol
- Vendor lock-in with no meaningful benefit given our Python agent layer

**Custom `useStreamingChat` hook** — hand-rolled SSE hook from the v0
prototype. Backend-agnostic: consumes any endpoint that emits the agreed
SSE event protocol. Replaces `useChat` entirely. See the Streaming
section below for bugs to fix before production.

**hey-api (`@hey-api/openapi-ts`)** — generates a typed TypeScript
client from FastAPI's `/openapi.json`. Provides type-safe request params
and response shapes for the bookings endpoints. Not used for the chat
endpoint (managed separately via the streaming hook + local state).

**Memory** is a backend concern deferred to a later phase. Candidates:
AWS Bedrock AgentCore Memory, mem0, or Strands' built-in memory. The
frontend is deliberately stateless between sessions.

### Responsibility split

| Concern | Handled by |
|---|---|
| Chat UI components | v0 prototype components (shadcn/ui) |
| SSE streaming + state | `useStreamingChat` hook |
| Typed HTTP client | hey-api (generated from OpenAPI) |
| In-session message state | Local React state (`useState`) |
| Multi-session memory | Future: AgentCore / mem0 (backend) |
| Agent logic, tool calls | Strands + Python FastAPI |

### Target structure

The richer component set from the v0 prototype replaces the originally
planned minimal three-file layout.

```
apps/web/
├── package.json
├── tsconfig.json
├── next.config.ts
├── env.ts                  # t3-env validated env vars
├── app/
│   ├── layout.tsx          # Root layout, metadata, DM Sans font
│   ├── page.tsx            # Responsive layout (sidebar + chat)
│   └── globals.css         # OKLCH color tokens, Tailwind base
├── components/
│   ├── app-sidebar.tsx     # Brand, new-chat, recent convos, address
│   ├── chat-container.tsx  # Orchestrates chat flow, scroll, loading
│   ├── chat-input.tsx      # Auto-expand textarea, Enter/stop button
│   ├── chat-message.tsx    # User/assistant bubbles + ReactMarkdown
│   ├── tool-cards.tsx      # 5 tool result cards (restaurant, booking…)
│   ├── welcome-screen.tsx  # Greeting + 4 suggestion chips
│   └── theme-provider.tsx  # next-themes wrapper
├── hooks/
│   ├── use-streaming-chat.ts  # Custom SSE hook (see bugs section)
│   ├── use-mobile.ts          # 768px breakpoint detection
│   └── use-toast.ts           # Toast state (observer pattern)
├── lib/
│   ├── types.ts            # ChatMessage, SSEEvent, ToolInvocation
│   ├── utils.ts            # cn() Tailwind merge helper
│   └── api.ts              # Generated typed client (do not hand-edit)
└── ui/                     # shadcn/ui primitives (accordion, badge…)
```

### API client

`lib/api.ts` is generated by hey-api from FastAPI's OpenAPI spec. It
covers `GET /bookings/{id}` and `DELETE /bookings/{id}`. The base URL is
read from `env.NEXT_PUBLIC_API_URL` (set in Vercel environment settings
to the API Gateway URL output by SST). For local dev it falls back to
`http://localhost:8000`.

The `POST /chat` endpoint is called via the `useStreamingChat` hook in
`chat-container.tsx` — not through the generated client — because
in-session message history is managed as local React state alongside the
streaming connection.

Regenerate after any backend schema change:
```bash
cd backend && uv run uvicorn app.main:app &
curl localhost:8000/openapi.json > ../apps/web/openapi.json
cd ../apps/web && bun run generate:client
```

### Chat UX behaviour

- Responses stream via SSE — text appears incrementally as the agent
  produces it, tool cards appear as tools complete
- Show `ToolLoadingIndicator` for each in-flight tool call
- Show a 3-dot bounce while the initial response chunk has not yet
  arrived
- `Enter` submits, `Shift+Enter` inserts a newline
- Input is disabled while streaming to prevent concurrency errors on the
  singleton agent
- Stop button aborts the in-flight request via `AbortController`

### v0 Prototype Migration Plan

**Source:** `github.com/Facundo-Martin/v0-restaurant-assistant-ui`

#### What to migrate as-is
All UI components, hooks, types, and theme are production-quality and
migrate without changes:
- `app/globals.css` → same path (OKLCH color tokens are the design system)
- `components/*.tsx` → same paths (all 7 components)
- `hooks/use-mobile.ts`, `hooks/use-toast.ts` → same paths
- `lib/types.ts`, `lib/utils.ts` → same paths
- `components/ui/` → same path (57 shadcn/ui primitives)

#### What to adapt
- `app/layout.tsx` — keep DM Sans font and metadata; remove v0 analytics
- `app/page.tsx` — keep responsive sidebar + chat layout; no changes
  needed to logic
- `components/chat-container.tsx` — change the hard-coded `/api/chat`
  endpoint to read from `env.NEXT_PUBLIC_API_URL + "/chat"`
- `hooks/use-streaming-chat.ts` — fix the three bugs documented below
  before connecting to the real FastAPI backend

#### What to discard
- `app/api/chat/route.ts` — the mock SSE backend; entirely replaced by
  the real FastAPI endpoint

---

## Streaming Implementation Analysis

### SSE wire format

The v0 prototype uses a custom SSE parser inside `useStreamingChat`. The
agreed event protocol (both sides must conform):

```
data: {"type":"text-delta","delta":"Hello"}\n\n
data: {"type":"tool-call-start","toolCallId":"t1","toolName":"createBooking","input":{...}}\n\n
data: {"type":"tool-result","toolCallId":"t1","output":{...}}\n\n
data: {"type":"tool-error","toolCallId":"t1","error":"..."}\n\n
data: {"type":"done"}\n\n
data: {"type":"error","error":"..."}\n\n
```

Each event is a single `data:` line terminated by `\n\n`. The FastAPI
backend must produce exactly this format.

### What works correctly

- **Chunk-boundary buffering**: `buffer += decoder.decode(value, { stream: true })` +
  `lines.pop()` correctly holds incomplete lines across TCP chunks.
- **Event dispatch**: the `switch` on `event.type` correctly handles all
  six event types.
- **Tool ordering**: a `Map<toolCallId, ToolInvocation>` preserves
  insertion order; `buildParts()` emits tools in the order they started.
- **AbortController**: `stop()` aborts the fetch; `AbortError` is caught
  and treated as a clean stop, not an error.
- **Incremental state updates**: `setMessages` updater function pattern
  avoids stale closure issues on each chunk.

### Bugs to fix before production

**Bug 1 — TextDecoder not flushed (drops multibyte characters)**

`new TextDecoder()` with `{ stream: true }` buffers incomplete UTF-8
byte sequences internally. After the read loop ends, the decoder's
internal buffer is never flushed. Any multibyte character (emoji,
accented character, CJK) whose bytes straddle a chunk boundary will be
silently dropped.

Fix: call `decoder.decode()` (no arguments) after the while loop exits
to flush the remaining bytes into `buffer` before final processing.

```ts
// After: while (true) { ... }
buffer += decoder.decode() // flush remaining bytes
```

**Bug 2 — CRLF line endings cause silent JSON parse failures**

The parser splits on `'\n'`. The SSE spec permits `\r`, `\n`, or `\r\n`
as line terminators. AWS API Gateway and some HTTP proxies emit `\r\n`.
When present, the `\r` becomes part of the JSON string and causes
`JSON.parse` to throw — caught silently by the `try/catch`, dropping
the event entirely.

Fix: strip `\r` from each line before parsing.

```ts
const data = trimmed.replace(/\r$/, '').slice(5).trim()
```

**Bug 3 — `tool-result` spreading `undefined` for unknown tool IDs**

```ts
case 'tool-result':
  toolInvocations.set(event.toolCallId, {
    ...toolInvocations.get(event.toolCallId)!, // non-null assertion
    state: 'complete',
    output: event.output,
  })
```

If a `tool-result` event arrives for a `toolCallId` that has no
corresponding `tool-call-start` (network reorder, dropped event), the
`Map.get` returns `undefined`. Spreading `undefined` in JS is a no-op —
the result is `{ state: 'complete', output: ... }` with `toolCallId`
and `toolName` missing. This renders as a broken tool card with no
crash.

Fix: guard with an existence check.

```ts
case 'tool-result': {
  const existing = toolInvocations.get(event.toolCallId)
  if (existing) {
    toolInvocations.set(event.toolCallId, {
      ...existing,
      state: 'complete',
      output: event.output,
    })
    updateAssistant()
  }
  break
}
```

### Known limitations (acceptable for now)

- **`messages` in `useCallback` deps**: `sendMessage` gets a new
  identity on every render because `messages` is a dependency. This is
  harmless (input is disabled during streaming, preventing double sends)
  but causes unnecessary re-renders. Can be refactored to a `useRef`
  mirror of messages in a later pass.
- **Single `data:` line per event only**: the parser does not accumulate
  multi-line SSE events (multiple consecutive `data:` fields). The
  FastAPI backend must emit exactly one `data:` line per event, which is
  the natural format for JSON payloads.
- **No SSE reconnect**: if the connection drops mid-stream, the hook
  surfaces an error. Automatic reconnect is not implemented. Acceptable
  given Lambda's 29-second API Gateway timeout and the short duration of
  individual agent responses.

### Deployment

Deployed to **Vercel** independently from the SST stack (not via
`sst.aws.Nextjs`). Set `NEXT_PUBLIC_API_URL` to the API Gateway URL in
Vercel's environment settings. CORS on the API Gateway is already
configured to `allowOrigins: ["*"]` with a TODO to tighten it to the
Vercel domain once known.
