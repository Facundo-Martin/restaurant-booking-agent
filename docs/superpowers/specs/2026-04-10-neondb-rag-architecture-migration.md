# NeonDB + LlamaIndex RAG Architecture Migration

**Date:** April 10, 2026
**Status:** Design Approved
**Author:** Facundo Martin

---

## Executive Summary

Migrate from AWS-heavy infrastructure (Aurora RDS + DynamoDB + Bedrock KB) to a unified, cost-efficient stack: **NeonDB PostgreSQL + LlamaIndex + OpenAI embeddings + Railway deployment**.

**Cost Impact:** 60-80% reduction (~$50-120/mo → ~$20-25/mo)
**Scope:** Full architecture revamp, implemented progressively by 6 phases
**Timeline:** Phase-based (no week estimates; tasks vary by effort)

---

## Problem Statement

**Current State:**
- Aurora RDS (vector store): $15-70/mo minimum cost
- DynamoDB (bookings): $5-20/mo
- Lambda + API Gateway: ~$15/mo
- WAF + networking: ~$10/mo
- **Total: $50-120/mo** (plus accidental charges if `sst dev` left running)

**Root Issue:** Overreliance on AWS managed services for a hobby/demo app. Each service adds operational complexity and minimum billing.

**Desired State:**
- Single PostgreSQL database (NeonDB) for all data: bookings, KB vectors, user preferences
- Serverless embeddings (OpenAI API) instead of Bedrock
- Simple container deployment (Railway) instead of Lambda + API Gateway
- No VPC, bastion, WAF, or other overhead
- **Target: ~$20-25/mo with scale-to-zero capabilities**

---

## Architecture Overview

### Data Flow

```
kb-documents/*.docx
  ↓
LlamaIndex (local, on deploy)
  ├─ Parse with DocxReader
  ├─ Chunk intelligently
  ├─ Generate embeddings (OpenAI API)
  └─ Store in NeonDB
       ↓
   NeonDB pgvector (vector store + relational data)
       ├─ documents (chunk_text, embedding, metadata)
       ├─ bookings (booking_id, user_id, restaurant_name, date, party_size, special_requests)
       ├─ users (user_id, email, dietary_restrictions, allergies, preferences)
       └─ S3 buckets (KB source docs, session state)
            ↓
   FastAPI (containerized) on Railway
       ├─ POST /chat → agent calls retrieve_documents() → queries NeonDB vectors
       ├─ GET /bookings/{id} → queries bookings table
       ├─ POST /bookings → creates booking, stores user preferences
       └─ SSE streaming responses
            ↓
   Frontend (Vercel)
```

### Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Database** | NeonDB (PostgreSQL) | Single source of truth: bookings, KB vectors, user data |
| **Vector Store** | pgvector extension | Semantic search for knowledge base |
| **Embeddings** | OpenAI text-embedding-3-small | Generate 1536-dim vectors for KB chunks |
| **Document Processing** | LlamaIndex | Parse .docx, chunk intelligently, orchestrate embeddings |
| **Backend Runtime** | FastAPI (containerized) | HTTP API with SSE streaming |
| **Deployment** | Railway | Container-based PaaS (replaces Lambda + API Gateway) |
| **Safety** | Bedrock Guardrail | Content moderation on model invocations (unchanged) |
| **Session Storage** | S3 | Conversation history (unchanged) |
| **Infrastructure** | SST (Pulumi) | IaC for NeonDB setup + ingestion jobs |
| **Local Dev** | Docker Compose + sst shell | Containerized backend with SST secret injection |

---

## Database Schema

**Schema Initialization Strategy:**
- **pgvector extension + `documents` table**: Created by SST infra code in Phase 1 (one-time setup, required for KB ingestion)
- **`users` and `bookings` tables**: Managed by SQLAlchemy ORM + Alembic migrations (Phase 3+)
  - This separation keeps infrastructure code focused on platform concerns
  - Alembic handles all future schema changes, rollbacks, and multi-environment consistency
  - ORM provides type safety and easier refactoring

### `documents` — Knowledge Base Vectors (Infra-Managed)

Created once in `infra/kb.ts` via psql command:

```sql
CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chunk_text TEXT NOT NULL,              -- Document chunk (e.g., menu item, description)
  embedding vector(1536),                -- OpenAI text-embedding-3-small output
  restaurant_name TEXT,                  -- Filter: which restaurant (e.g., "The Smoking Ember")
  document_source TEXT,                  -- Source file name (e.g., "The Smoking Ember.docx")
  chunk_index INT,                       -- Order within document (for context preservation)
  metadata JSONB,                        -- Flexible: section, category, etc.
  created_at TIMESTAMP DEFAULT NOW()
);

-- Vector index (HNSW) is infrastructure-critical for KB semantic search
CREATE INDEX doc_embedding_idx ON documents USING hnsw (embedding vector_cosine_ops);

-- Regular B-tree indexes deferred to Phase 3 (added with SQLAlchemy repository layer)
-- TODO (Phase 3): Add index on restaurant_name for filtering queries
```

### `users` — User Profiles & Preferences (ORM-Managed via Alembic)

Defined and created via SQLAlchemy ORM:

```python
# backend/app/models/user.py
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, JSON, ARRAY
from datetime import datetime
from uuid import UUID, uuid4

class User(Base):
    __tablename__ = "users"

    user_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String, unique=True)

    # Preferences stored as first-class columns (1:1 relationship, no separate table)
    dietary_restrictions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    allergies: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    accessibility_needs: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    other_preferences: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### `bookings` — Restaurant Reservations (ORM-Managed via Alembic)

Defined and created via SQLAlchemy ORM:

```python
# backend/app/models/booking.py
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, JSON, ForeignKey, Index
from datetime import datetime
from uuid import UUID, uuid4

class Booking(Base):
    __tablename__ = "bookings"

    booking_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.user_id"))
    restaurant_name: Mapped[str] = mapped_column(String)
    date: Mapped[str] = mapped_column(String)  # YYYY-MM-DD format
    party_size: Mapped[int]
    special_requests: Mapped[dict] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_bookings_user_date", "user_id", "date"),
        Index("idx_bookings_restaurant_date", "restaurant_name", "date"),
    )
```

### S3 Buckets (Unchanged)

- **KbDocuments**: Source `.docx` files uploaded by admin
- **AgentSessions**: Conversation history (JSON per session_id, expires after 30 days)

---

## Component Details

### 1. NeonDB Setup

**Connection:** Managed externally (Neon dashboard); SST Secret stores connection string.

**Schema Initialization (idempotent) — pgvector + documents table only:**

⚠️ **Important:** Only the `documents` table (for KB vectors) is created here. The `users` and `bookings` tables are managed by SQLAlchemy ORM + Alembic migrations (see Phase 3+). This separation keeps infrastructure code focused and enables proper schema versioning.

```typescript
// infra/kb.ts
const neonConnectionString = new sst.Secret("NeonConnectionString");

// Create NeonDB as SST Linkable resource (allows Python code to use: from sst import Resource)
const neonDb = sst.Linkable.wrap(
  "NeonDatabase",
  () => ({
    properties: { connectionString: neonConnectionString }
  })
);

const initSchema = new command.local.Command(
  "InitPgvectorSchema",
  {
    create: $resolve(neonConnectionString).apply((connStr) => `
      psql "${connStr}" -c "CREATE EXTENSION IF NOT EXISTS vector;"
      psql "${connStr}" << 'EOF'
        CREATE TABLE IF NOT EXISTS documents (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          chunk_text TEXT NOT NULL,
          embedding vector(1536),
          restaurant_name TEXT,
          document_source TEXT,
          chunk_index INT,
          metadata JSONB,
          created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS doc_embedding_idx ON documents USING hnsw (embedding vector_cosine_ops);
        CREATE INDEX IF NOT EXISTS doc_restaurant_idx ON documents(restaurant_name);
      EOF
    `),
  }
);

export { neonDb };
```

**Cost:** $15-25/mo (includes compute + storage for all tables)

---

### 2. Knowledge Base Ingestion

**Process (runs once at deploy time):**

1. **Parse**: LlamaIndex `DocxReader` reads `kb-documents/*.docx`
2. **Chunk**: LlamaIndex splits respecting document structure (not naive line-by-line)
3. **Embed**: OpenAI `text-embedding-3-small` API generates 1536-dim vectors
4. **Store**: Insert chunks + embeddings + metadata into `documents` table
5. **Idempotent**: Script checks if documents exist; skips re-ingestion on redeploys

**Script** (`backend/scripts/ingest_kb.py`):
```python
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding
from sst import Resource

# Load all documents from kb-documents/
documents = SimpleDirectoryReader("kb-documents/").load_data()

# Get connection string from SST Resource (no os.getenv needed)
neon_connection_string = Resource.NeonDatabase.connectionString

# Create NeonDB vector store
vector_store = PGVectorStore.from_connection_string(
    connection_string=neon_connection_string,
    table_name="documents"
)

# Create index (LlamaIndex handles chunking, embedding, storage)
index = VectorStoreIndex.from_documents(
    documents,
    vector_store=vector_store,
    embed_model=OpenAIEmbedding(model="text-embedding-3-small")
)

print(f"✓ Ingested {len(documents)} documents into NeonDB")
```

**SST Integration:**
```typescript
// infra/kb.ts
const ingestKb = new command.local.Command(
  "IngestKnowledgeBase",
  {
    create: $resolve([neonConnectionString, openaiKey]).apply(([connStr, key]) => `
      cd backend && \
      NEON_CONNECTION_STRING="${connStr}" \
      OPENAI_API_KEY="${key}" \
      uv run python scripts/ingest_kb.py
    `),
  },
  { dependsOn: [initSchema] }
);
```

**Cost:** ~$1-5/mo (one-time at deploy; depends on KB size and re-indexing frequency)

---

### 3. Retrieve Tool (Placeholder Pattern)

**Interface (defined now, implementation deferred):**

```python
# backend/app/tools/retrieve.py

from strands import tool

@tool
def retrieve_documents(
    query: str,
    restaurant_name: str | None = None,
    top_k: int = 5
) -> list[dict]:
    """
    Retrieve the most relevant restaurant documents using semantic search.

    Args:
        query: The user's question or search term.
        restaurant_name: Optional filter to search a specific restaurant.
        top_k: Number of documents to return.

    Returns:
        List of relevant document chunks with metadata.
    """
    # TODO: Implement with SQLAlchemy repository pattern (Phase 3)
    # Phase 1: Mock implementation
    # Phase 3: Real pgvector semantic search
    # Future: Reranking, hybrid search, etc.

    return [
        {
            "text": f"Mock result for '{query}'",
            "restaurant": restaurant_name or "Any",
            "similarity": 0.95
        }
    ]
```

**Phase 3 Implementation (with SQLAlchemy):**
```python
# Phase 3: Real implementation using SQLAlchemy repository pattern
from app.repositories.documents import DocumentRepository
from app.models.embeddings import get_embedding

@tool
def retrieve_documents(query: str, restaurant_name: str | None = None, top_k: int = 5) -> list[dict]:
    query_embedding = get_embedding(query)  # Convert query to vector
    repo = DocumentRepository()
    results = repo.search_by_embedding(query_embedding, restaurant_name, top_k)
    return [
        {
            "text": doc.chunk_text,
            "restaurant": doc.restaurant_name,
            "similarity": float(doc.similarity_score)
        }
        for doc in results
    ]
```

---

### 4. Backend (FastAPI Containerized)

**Handler (entry point):**
```python
# backend/app/handler.py
from mangum import Mangum
from app.main import app

handler = Mangum(app)
```

**Main app (unchanged, works locally and in Railway):**
```python
# backend/app/main.py
from fastapi import FastAPI
from app.api.routes.chat import router as chat_router

app = FastAPI()
app.include_router(chat_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Dockerfile:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Local Dev (Docker Compose):**
```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - NEON_CONNECTION_STRING
      - OPENAI_API_KEY
      - BEDROCK_GUARDRAIL_ID
      - APP_STAGE
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Deployment (Railway):** Same Docker image, env vars set via Railway dashboard.

---

### 5. Infrastructure Code (Cleanup + NeonDB)

**Phase 0 Actions (disable old AWS services):**

```typescript
// sst.config.ts
const app = new sst.App();

// ❌ DISABLED (Phase 0 cleanup)
// const vpc = await import("./infra/networking");
// const api = await import("./infra/api");
// const ai = await import("./infra/ai");

// ✅ KEEP
const storage = await import("./infra/storage");  // S3 buckets only
const kb = await import("./infra/kb");             // NeonDB setup

app.setDefaultFunctionProps({
  runtime: "python3.11",
  timeout: "60 seconds",
  environment: { APP_STAGE: $app.stage }
});
```

**Infra Files (Post-Cleanup):**

| File | Status | Content |
|---|---|---|
| `infra/storage.ts` | ✏️ Refactor | S3 buckets only (remove DynamoDB, Aurora) |
| `infra/kb.ts` | ✨ NEW | NeonDB schema init + LlamaIndex ingestion |
| `infra/ai.ts` | ⚠️ Reduce | Bedrock Guardrail only (remove KB setup) |
| `infra/web.ts` | ⚠️ Update | Remove WAF association |
| `infra/api.ts` | ❌ DELETE | No Lambda functions |
| `infra/security.ts` | ❌ DELETE | No WAF |
| `infra/networking.ts` | ❌ DELETE | No VPC |

---

## Development Workflow

### Setup (First Time)

```bash
# 1. Clone repo, install deps
git clone ...
cd restaurant-booking-agent
pnpm install

# 2. Create .env with NeonDB connection string (or get from manager)
# NEON_CONNECTION_STRING=postgres://...
# OPENAI_API_KEY=sk-...
# BEDROCK_GUARDRAIL_ID=...

# 3. Run backend with SST secret injection + Docker
pnpm dev:api
# Runs: sst shell -- docker-compose up
# SST injects secrets → Docker runs FastAPI on localhost:8000

# 4. In another terminal, run frontend
cd apps/web && npm run dev
```

### Local Testing

```bash
# Test retrieve tool (mock phase)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What'\''s on the menu at The Smoking Ember?"}'

# Test database directly
sst shell -- psql $NEON_CONNECTION_STRING -c "SELECT COUNT(*) FROM documents;"
```

### Deployment to Railway

```bash
# 1. Connect repo to Railway (via web dashboard)
# 2. Set env vars in Railway dashboard
# 3. Deploy
railway deploy
# Railway automatically builds Docker image + deploys

# Or use CLI
railway login
railway up
```

---

## Implementation Phases

### Phase 0: Cleanup & Disable AWS Resources

**Goal:** Stop spinning up expensive services on `sst dev`

**Tasks:**
- [ ] Comment out `infra/networking.ts`, `infra/api.ts`, old `infra/ai.ts` in `sst.config.ts`
- [ ] Delete `infra/security.ts` file
- [ ] Delete `infra/networking.ts` file
- [ ] Verify: `sst dev` only starts S3 buckets (no RDS, Lambda, VPC charges)

---

### Phase 1: NeonDB Setup + Placeholder Retrieve

**Goal:** Database ready, placeholder tool interface

**Tasks:**
- [ ] Provision NeonDB, store connection string in SST Secret
- [ ] Create `infra/kb.ts` with pgvector schema init
- [ ] Update database schema: add `users`, `bookings`, `documents` tables
- [ ] Create `backend/app/tools/retrieve.py` with placeholder implementation
- [ ] Create `docker-compose.yml` for local dev
- [ ] Update `package.json`: `"dev:api": "sst shell -- docker-compose up"`
- [ ] Test: `pnpm dev:api` runs FastAPI in Docker with SST env vars

---

### Phase 2: KB Ingestion Pipeline

**Goal:** Documents indexed in NeonDB

**Tasks:**
- [ ] Create `backend/scripts/ingest_kb.py` (LlamaIndex + OpenAI)
- [ ] Add ingestion command to `infra/kb.ts`
- [ ] Test: `sst shell -- python backend/scripts/ingest_kb.py` populates `documents` table
- [ ] Verify: Query NeonDB directly — confirm chunks + embeddings stored

---

### Phase 3: Implement Retrieve Tool + SQLAlchemy Repository

**Goal:** Real semantic search via SQLAlchemy

**Tasks:**
- [ ] Create `backend/app/repositories/documents.py` (SQLAlchemy for `documents` table)
- [ ] Implement real `retrieve_documents()` tool with pgvector similarity search
- [ ] Create embedding utilities (`backend/app/models/embeddings.py`)
- [ ] Add database indexes for query optimization (B-tree on `restaurant_name`, run via Alembic migration)
- [ ] Test: Agent calls retrieve, gets real results from NeonDB with acceptable latency

---

### Phase 4: Agent Integration & Testing

**Goal:** Evals pass with new architecture

**Tasks:**
- [ ] Update `backend/app/agent.py` to use real retrieve tool
- [ ] Run existing evals: `pnpm eval:braintrust:discovery`, `eval:strands:discovery`
- [ ] Fix any failures (relevance, chunking, guardrail integration)
- [ ] Benchmark: Verify semantic search latency acceptable (<500ms)

---

### Phase 5: AWS Cleanup & Shutdown

**Goal:** Remove old AWS resources entirely

**Tasks:**
- [ ] Delete `infra/api.ts` file
- [ ] Delete `infra/security.ts` file (already done in Phase 0)
- [ ] Simplify `infra/storage.ts` — remove DynamoDB, remove Aurora RDS
- [ ] Simplify `infra/ai.ts` — remove Bedrock KB setup, keep only Guardrail
- [ ] Update `infra/web.ts` — remove WAF association TODO
- [ ] `sst remove` — tear down all remaining AWS resources
- [ ] Verify: All expensive services (Aurora, DynamoDB, Lambda, API Gateway) deleted

---

### Phase 6: Railway Deployment

**Goal:** Live on Railway (not AWS)

**Tasks:**
- [ ] Connect GitHub repo to Railway (via web dashboard)
- [ ] Set env vars in Railway: `NEON_CONNECTION_STRING`, `OPENAI_API_KEY`, `BEDROCK_GUARDRAIL_ID`
- [ ] Deploy: `railway deploy`
- [ ] Test: Chat endpoint from Railway URL
- [ ] Monitor: Check Railway logs, billing

---

## Cost Breakdown

### Monthly Costs (Post-Migration)

| Component | Cost | Notes |
|---|---|---|
| **NeonDB** | $15-20 | Base serverless plan; includes all tables |
| **OpenAI Embeddings** | $1-5 | ~$0.02 per 1M tokens; re-index on demand |
| **Railway** | $0-5 | Free tier available; paid tier $5-25/mo |
| **S3 (sessions)** | <$1 | Minimal usage; expires after 30 days |
| **Bedrock (guardrail only)** | ~$1 | Invoked per model call; minimal overhead |
| **Total** | **$20-25/mo** | 60-80% reduction vs. current $50-120 |

### Migration Savings

| Service | Current | New | Status |
|---|---|---|---|
| Aurora RDS | $15-70 | → Included in NeonDB | ✅ Eliminated |
| DynamoDB | $5-20 | → Included in NeonDB | ✅ Eliminated |
| Lambda | ~$5 | → Included in Railway | ✅ Eliminated |
| API Gateway | ~$5 | → Included in Railway | ✅ Eliminated |
| WAF | $5 | → $0 | ✅ Eliminated |
| Bedrock KB | ~$10 | → $0 (use LlamaIndex) | ✅ Eliminated |
| **Total Savings** | — | **~$45-95/mo** | ✅ 60-80% reduction |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **pgvector performance** | Slow semantic search on large KB | Phase 2: benchmark with full 12 docs; optimize indexes if needed |
| **LlamaIndex ingestion fails** | Missing documents in KB | Phase 2: test on all doc formats; add error handling + retry logic |
| **OpenAI API rate limits** | Embedding generation blocked | Set up usage alerts in OpenAI dashboard; start Phase 2 with small batch |
| **NeonDB connection pool exhaustion** | DB connection errors under load | Use SQLAlchemy connection pooling; monitor active connections |
| **Railway deployment issues** | API unavailable | Phase 6: test locally first; have rollback plan (keep old Lambda as backup) |
| **Bedrock Guardrail integration** | Guardrail doesn't work post-migration | Phase 4: test guardrail with real agent; verify stop_reason handling |

---

## Success Criteria

**Phase 0 Complete:**
- [ ] `sst dev` only runs S3 buckets
- [ ] No RDS, Lambda, VPC, or WAF resources spinning up

**Phase 1 Complete:**
- [ ] `pnpm dev:api` runs FastAPI in Docker
- [ ] SST env vars injected (NEON_CONNECTION_STRING, etc.)
- [ ] Placeholder retrieve tool returns mock data

**Phase 2 Complete:**
- [ ] `documents` table populated with KB chunks + embeddings
- [ ] `SELECT COUNT(*) FROM documents;` returns >0
- [ ] Semantic search query latency <500ms

**Phase 3 Complete:**
- [ ] Real `retrieve_documents()` tool returns actual KB results
- [ ] SQLAlchemy repository pattern implemented
- [ ] Agent integration tests pass

**Phase 4 Complete:**
- [ ] `pnpm eval:braintrust:discovery` passes with >80% success rate
- [ ] Semantic relevance benchmarks meet expectations

**Phase 5 Complete:**
- [ ] `sst remove` completes successfully
- [ ] All AWS resources deleted
- [ ] CloudWatch logs archived or deleted

**Phase 6 Complete:**
- [ ] Chat endpoint live on Railway URL
- [ ] Streaming responses work end-to-end
- [ ] Monitoring/alerts set up on Railway

---

## Appendix: Decision Log

### Why NeonDB over Aurora?
- **Cost**: Scale-to-zero; Aurora has $15-70/mo minimum even when idle
- **Simplicity**: Managed Postgres; no VPC/bastion complexity
- **Portability**: Standard Postgres; can migrate elsewhere if needed

### Why LlamaIndex over custom chunking?
- **Robustness**: Handles edge cases (mid-sentence splits, context windows)
- **Ecosystem**: Integrates with OpenAI, pgvector, and many LLMs
- **Battle-tested**: Used in production RAG systems (RagRabbit on Neon uses it)

### Why OpenAI embeddings over Bedrock?
- **Cost**: $0.02 per 1M tokens (vs. Bedrock's ~$10/mo baseline)
- **Flexibility**: Can swap to Cohere, Hugging Face, etc. without re-architecting
- **Quality**: text-embedding-3-small ranks high on MTEB leaderboard

### Why Railway over ECS/Fargate?
- **Cost**: $0-5/mo vs. $20-50/mo for managed container services
- **DevX**: `git push` deployment; no AWS CLI required
- **Simplicity**: Same Docker image locally + production; no orchestration

### Why SQLAlchemy repository pattern?
- **Decoupling**: Database logic separate from agent code
- **Testability**: Mock repository for unit tests
- **Flexibility**: Swap implementations (pgvector → Pinecone, etc.) without breaking tools

### Why defer B-tree indexes to Phase 3?
- **Vector index (HNSW) is infrastructure-critical**: Required for KB semantic search during ingestion + retrieval
- **B-tree indexes are application-layer optimizations**: Belong with the repository implementation in Phase 3
- **Separation of concerns**: Infra code creates the table structure; ORM handles indexing strategy
- **Pragmatism**: By Phase 3, you'll know actual query patterns and can add indexes intelligently
- **Low cost of deferral**: Indexes can be added anytime via Alembic migrations without breaking the system

---

## Approval

- [ ] Facundo Martin — Approved on 2026-04-10

---

**Next Step:** Implementation planning (Phase 0 kickoff)
