# Scripts

## Initializing the Aurora pgvector Schema

Run once per stage before deploying the Knowledge Base.

### Prerequisites

- AWS credentials configured
- `psql` installed (`brew install libpq`)
- SST tunnel running (see below)

### Steps

**1. Start the SST tunnel** (keeps running — leave this terminal open)

```bash
npx sst tunnel --stage <stage>
```

"Waiting for connections..." means it's ready.

**2. Get the Aurora endpoint and password**

- Endpoint: SST deploy output (`auroraEndpoint`) or AWS Console → RDS → your cluster → "Endpoint & port"
- Password: AWS Console → Secrets Manager → your cluster's secret → "Retrieve secret value"

**3. Connect with psql** (new terminal)

```bash
psql --host <auroraEndpoint> --port 5432 --username postgres -d restaurant_booking_agent
```

**4. Run the init script**

```sql
\i scripts/init-db.sql
```

**5. Verify**

```sql
\d bedrock_integration.bedrock_kb
\di bedrock_integration.*
```

You should see the table with columns `id`, `embedding`, `chunks`, `metadata`, `custom_metadata` and three indexes (HNSW + two GIN).

**6. Re-enable the Knowledge Base infra**

Once the schema is initialized, uncomment `ai` and `api` in `sst.config.ts` and redeploy.

---

## Syncing KB Documents to S3

After deploying with the KB enabled, upload the documents in `kb-documents/` and trigger ingestion:

```bash
./scripts/sync-kb.sh <stage>
# Example: ./scripts/sync-kb.sh dev
```

The script:
1. Finds the `KbDocuments` S3 bucket by SST tags (no hardcoded names)
2. Syncs `kb-documents/*.docx` to the bucket
3. Starts a Bedrock ingestion job and polls until complete

> **Note:** Steps 2–3 of the ingestion job are commented out in `sync-kb.sh` until `infra/ai.ts` is deployed. Once the KB is live, fill in `KB_ID` and `DATA_SOURCE_ID` from the SST deploy outputs and uncomment that section.

---

## Testing the Knowledge Base

Requires `infra/ai.ts` to be deployed. Uses `sst shell` to inject `Resource.RestaurantKB.id` automatically.

```bash
# Retrieve-only — verify vector search is working
bun sst shell --stage dev -- bun run scripts/test-kb.ts retrieve "What Italian restaurants are available?"

# Retrieve-and-generate — full RAG response via Claude Haiku
bun sst shell --stage dev -- bun run scripts/test-kb.ts generate "What Italian restaurants are available?"
```

> **Dependency:** `@aws-sdk/client-bedrock-agent-runtime` must be installed at the root (`bun add @aws-sdk/client-bedrock-agent-runtime`).
