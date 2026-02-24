# Building the Infrastructure — A Progressive Guide

This guide walks through the infrastructure the same way it was built: one piece at a time, deployed and verified before moving to the next. Each section covers the *why* behind a decision, shows the code, and ends with a way to confirm it works.

By the end, you will have a running vector database, a Bedrock Knowledge Base with documents indexed into it, and an API backed by a Strands agent — and you will understand why every part is configured the way it is.

---

## Part 1 — Private Networking

### Why we need a VPC

Most AWS services are accessible over the public internet using IAM credentials — Lambda, DynamoDB, Bedrock, S3. You do not need a VPC for any of them.

Aurora Serverless v2 is different. It only accepts TCP connections from within a VPC. There is no public endpoint option. So the first thing we provision is a VPC to give Aurora a home.

Lambda is intentionally *not* placed inside the VPC. Lambda reaches DynamoDB and Bedrock directly over AWS public endpoints using IAM — there is no reason to route that traffic through the VPC. Keeping Lambda outside the VPC avoids the cold-start latency penalty (~100–200ms) that comes with VPC-attached functions, and means we do not need a NAT gateway for Lambda egress. NAT gateways cost ~$32/month in fixed charges — skipping it by keeping Lambda outside the VPC is a deliberate cost decision.

The VPC exists for one reason: to host Aurora in private subnets.

### The bastion host

There is a bootstrapping problem with Aurora: the database needs a schema (a specific table, extension, and indexes) before Bedrock can use it, but nothing can create that schema until the cluster is running. We need a way to connect to Aurora and run SQL against it.

The `bastion: true` option on the VPC provisions a small EC2 instance in the public subnet and wires up `sst tunnel`, which creates an SSH port-forward to the private subnets. With the tunnel running, you can connect to Aurora from your local machine as if it were listening on localhost — without exposing the cluster to the public internet.

> We will revisit schema initialization in Part 3, where we automate it as a Pulumi command. The bastion is a fallback for interactive debugging and manual inspection.

```typescript
// infra/networking.ts

// VPC for private networking — hosts the Aurora cluster in private subnets.
// Lambda is NOT placed in the VPC; it reaches DynamoDB and Bedrock over IAM/public endpoints.
// bastion: true provisions an EC2 instance in the public subnet, enabling sst tunnel
// for direct psql access during schema initialization and debugging.
const vpc = new sst.aws.Vpc("Vpc", { bastion: true });

export { vpc };
```

At this point you can deploy just the VPC:

```bash
npx sst deploy --stage dev
```

It will be fast — a VPC and a bastion host. Nothing interesting yet, but the foundation is in place.

---

## Part 2 — Aurora Serverless v2

### Why Aurora over OpenSearch Serverless

The original design used Amazon OpenSearch Serverless (OSS) as the vector store for the Bedrock Knowledge Base. OSS was replaced for one concrete reason: cost floor.

OSS VECTORSEARCH collections require a minimum of **2 indexing OCUs + 2 search OCUs**, billed continuously regardless of whether any queries are running. At current pricing that is approximately **$345/month at zero traffic**.

Aurora Serverless v2 at 0.5 ACU minimum costs approximately **$22/month** in compute, plus ~$0.10/GB-month for storage. When combined with `removal: "remove"` in the SST config — which tears down all resources when you run `sst remove --stage dev` — the effective cost for a dev environment that is idle between sessions approaches zero.

Bedrock Knowledge Base supports both OSS and Aurora (via pgvector) as vector stores. The swap is entirely at the infrastructure layer; the agent code does not change.

### The Aurora config

```typescript
// infra/storage.ts

import { vpc } from "./networking";

// Holds the .docx source files that Bedrock ingests into the Knowledge Base
const kbBucket = new sst.aws.Bucket("KbDocuments");

// Aurora Serverless v2 cluster — vector store backing the Bedrock Knowledge Base via pgvector
const rds = new sst.aws.Aurora("VectorStore", {
  engine: "postgres",
  dataApi: true,   // required — explained below
  vpc,
  scaling: { min: "0.5 ACU", max: "1 ACU" },
});
```

**`dataApi: true` — the most important config on this resource.**

The RDS Data API exposes Aurora over HTTPS, allowing SQL to be executed with IAM credentials — no TCP connection, no connection pool, no VPN required. Two things depend on this:

1. **Bedrock Knowledge Base** uses the Data API to write embeddings during ingestion and read them during retrieval. Without `dataApi: true`, Bedrock simply cannot reach the cluster.
2. **Schema initialization** (Part 3) and **test scripts** (Part 4) both use the Data API to run SQL without needing the bastion tunnel.

**`scaling: { min: "0.5 ACU", max: "1 ACU" }`**

0.5 ACU is the minimum Aurora Serverless v2 unit — roughly 1 GB of RAM. Sufficient for embedding storage and retrieval at low traffic volumes. The max is capped at 1 ACU for dev to limit cost; a production environment would want at least 8–16 ACU max to handle concurrent ingestion and query load without throttling.

### DynamoDB — bookings storage

While we are in `storage.ts`, we also provision the DynamoDB table for restaurant reservations:

```typescript
// Stores restaurant reservations
const table = new sst.aws.Dynamo("Bookings", {
  fields: {
    booking_id: "string",
    user_id: "string",
    restaurant_name: "string",
    date: "string",
  },
  primaryIndex: { hashKey: "booking_id", rangeKey: "restaurant_name" },
  globalIndexes: {
    // Enables queries like "all bookings at Restaurant X on date Y" without a full table scan
    ByRestaurantDate: { hashKey: "restaurant_name", rangeKey: "date" },
    // Enables queries like "all bookings for user X"
    ByUser: { hashKey: "user_id", rangeKey: "date" },
  },
});

export { table, kbBucket, rds };
```

DynamoDB is the right tool for bookings because the access pattern is simple: create a booking with a generated ID, look it up by ID, delete it. DynamoDB handles this at sub-millisecond latency with zero operational overhead. Using Aurora for both the vector store and the bookings table would work, but would add VPC routing complexity, connection pooling concerns, and cold-start latency on the Lambda side.

The two GSIs (`ByRestaurantDate`, `ByUser`) are added now rather than later. DynamoDB GSIs can be added after a table has data, but doing it at table creation is simpler and avoids a table modification + backfill operation. The agent will need "all bookings at this restaurant" and "all bookings for this user" queries; without the GSIs those queries would require a full table scan.

Deploy this change:

```bash
npx sst deploy --stage dev
```

SST will output the Aurora endpoint. You now have a running Postgres cluster — but it has no schema yet. That comes next.

---

## Part 3 — Initializing the pgvector Schema

### The bootstrapping problem

Bedrock Knowledge Base expects a very specific schema inside Aurora before it can store or retrieve embeddings:

- The `vector` extension must be installed (pgvector)
- A schema named `bedrock_integration` must exist
- A table named `bedrock_kb` must exist with exact column names that match the KB's `fieldMapping` config
- An HNSW index on the `embedding` column for fast approximate nearest-neighbour search
- GIN indexes on `chunks` and `custom_metadata` for hybrid text + metadata filtering

None of this is created automatically. Aurora is just a blank Postgres database when it first provisions.

### The SQL

```sql
-- scripts/init-db.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS bedrock_integration;

CREATE TABLE IF NOT EXISTS bedrock_integration.bedrock_kb (
  id              uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
  embedding       vector(1024),   -- 1024 dims matches Amazon Titan Embed Text v2
  chunks          text    NOT NULL,
  metadata        json    NOT NULL,
  custom_metadata jsonb
);

-- HNSW for fast approximate nearest-neighbour search (cosine distance)
-- ef_construction=256 improves recall at the cost of slightly longer index build time
CREATE INDEX IF NOT EXISTS bedrock_kb_embedding_idx
  ON bedrock_integration.bedrock_kb
  USING hnsw (embedding vector_cosine_ops) WITH (ef_construction=256);

-- GIN for full-text keyword search — Bedrock uses this for hybrid queries
CREATE INDEX IF NOT EXISTS bedrock_kb_chunks_idx
  ON bedrock_integration.bedrock_kb
  USING gin (to_tsvector('simple', chunks));

-- GIN for custom metadata filtering
CREATE INDEX IF NOT EXISTS bedrock_kb_custom_metadata_idx
  ON bedrock_integration.bedrock_kb
  USING gin (custom_metadata);
```

**Why these indexes?**

The HNSW index on `embedding` is the core of vector search. HNSW (Hierarchical Navigable Small World) is the standard algorithm for approximate nearest-neighbour lookup in pgvector. `vector_cosine_ops` specifies cosine distance, which matches how Titan Embed v2 computes similarity between embeddings. Without this index, every retrieval query would require a sequential scan across every row — unusable at any meaningful document count.

The GIN index on `chunks` enables full-text keyword search alongside vector search. Bedrock Knowledge Base supports hybrid retrieval (semantic + keyword); the GIN index over `to_tsvector('simple', chunks)` is what powers the keyword side.

The GIN index on `custom_metadata` allows filtering retrieved chunks by arbitrary metadata key-value pairs. Useful when the KB contains documents from multiple sources and you want to restrict retrieval to a specific subset.

**Why `IF NOT EXISTS` on everything?**

Every statement is idempotent. This schema will be run again if the stack is torn down and recreated (which happens with `removal: "remove"` on every `sst remove`). `IF NOT EXISTS` makes re-running safe — no errors, no data loss.

### Automating schema init as a Pulumi command

You could run this SQL manually: start the bastion tunnel, connect with `psql`, paste the file. That works once. But it breaks CI, breaks teammates onboarding onto a new stage, and breaks the entire "one command to deploy" promise.

The better approach: make schema initialization part of the Pulumi deployment graph itself. The `@pulumi/command` provider lets you run an arbitrary shell command as a step in the graph — Pulumi treats it like a resource, tracks whether it has run, and respects `dependsOn`.

```typescript
// infra/ai.ts (excerpt)

import * as command from "@pulumi/command";
import { rds } from "./storage";

// Initialize pgvector schema in Aurora via the RDS Data API.
// Data API is accessible directly from the deployer's machine with IAM credentials —
// no tunnel or bastion connection needed.
// All statements use IF NOT EXISTS so this is idempotent across re-deploys.
const initSchema = new command.local.Command(
  "InitDbSchema",
  {
    create: $resolve([rds.clusterArn, rds.secretArn, rds.database]).apply(
      ([clusterArn, secretArn, database]) => {
        const exec = (sql: string) =>
          `aws rds-data execute-statement --resource-arn ${clusterArn} --secret-arn ${secretArn} --database ${database} --sql "${sql}" --profile iamadmin-general --region us-east-1`;

        return [
          exec("CREATE EXTENSION IF NOT EXISTS vector"),
          exec("CREATE SCHEMA IF NOT EXISTS bedrock_integration"),
          exec("CREATE TABLE IF NOT EXISTS bedrock_integration.bedrock_kb (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), embedding vector(1024), chunks text NOT NULL, metadata json NOT NULL, custom_metadata jsonb)"),
          exec("CREATE INDEX IF NOT EXISTS bedrock_kb_embedding_idx ON bedrock_integration.bedrock_kb USING hnsw (embedding vector_cosine_ops) WITH (ef_construction=256)"),
          exec("CREATE INDEX IF NOT EXISTS bedrock_kb_chunks_idx ON bedrock_integration.bedrock_kb USING gin (to_tsvector('simple', chunks))"),
          exec("CREATE INDEX IF NOT EXISTS bedrock_kb_custom_metadata_idx ON bedrock_integration.bedrock_kb USING gin (custom_metadata)"),
        ].join(" &&\n");
      },
    ),
  },
  // The Data API requires a running Aurora *instance*, not just the cluster control plane.
  // dependsOn ensures Pulumi waits for the instance to finish provisioning before
  // attempting any SQL calls.
  { dependsOn: [rds.nodes.instance] },
);
```

**Why `$resolve([...]).apply(...)`?**

`rds.clusterArn`, `rds.secretArn`, and `rds.database` are `Output<T>` values — Pulumi's async wrapper for things that do not exist until AWS provisions the resource. You cannot build a shell command string from them directly; you have to wait for them to resolve. `$resolve()` converts SST outputs to Pulumi outputs. `.apply()` receives the resolved values and returns the final string once all three are known.

**Why `dependsOn: [rds.nodes.instance]`?**

This is a subtle but critical distinction. Pulumi tracks the Aurora cluster and the Aurora instance as separate resources. The cluster ARN is available as soon as the cluster control plane is created — but the Data API requires an actual running instance before it accepts SQL. Without this `dependsOn`, Pulumi might start executing `aws rds-data execute-statement` while the instance is still initializing, and every call will fail with a "Database not available" error.

Deploy again:

```bash
npx sst deploy --stage dev
```

You will see Pulumi execute the six SQL statements in sequence after the Aurora instance finishes provisioning.

### Testing the schema: `scripts/test-db.ts`

Before moving on to the Knowledge Base, verify the schema is correct. A misconfigured table or missing index will cause cryptic Bedrock errors later — better to catch it here.

```bash
bun sst shell --stage dev -- bun run scripts/test-db.ts
```

Expected output:
```
Cluster: arn:aws:rds:us-east-1:123456789012:cluster:...
Database: restaurant_booking_agent_dev
---
✓ vector extension
✓ bedrock_integration schema
✓ bedrock_kb table
✓ hnsw embedding index (bedrock_kb_embedding_idx)
✓ gin chunks index (bedrock_kb_chunks_idx)
✓ gin metadata index (bedrock_kb_custom_metadata_idx)

6/6 checks passed
```

**Why `sst shell`?**

The script reads `Resource.VectorStore.clusterArn`, `Resource.VectorStore.secretArn`, and `Resource.VectorStore.database` — values injected by SST's link system. `sst shell` injects those same bindings into the current process, so the script receives the exact same cluster coordinates that Lambda will receive at runtime. Running it through `sst shell` also validates the injection mechanism itself, not just the database contents.

**Why the Data API instead of a `psql` connection?**

Both would verify the schema. The Data API also validates that: IAM credentials are working, the Data API is enabled on the cluster, and the credential secret is accessible. These are the same conditions Bedrock will rely on during ingestion. Passing all six checks means the Knowledge Base setup will not hit IAM or connectivity errors when it runs.

If any check fails, the output shows exactly which object is missing and what was returned instead. You know whether to re-run schema init or investigate a permissions issue — no manual database inspection required.

---

## Part 4 — The Bedrock Knowledge Base

### What a Knowledge Base does

The Strands agent needs to answer questions like "what Italian restaurants are available?" and "does Bella Roma have vegetarian options?". It does not know this from its training data — it learns it from the `.docx` files in `kb-documents/`.

A Bedrock Knowledge Base automates the full RAG pipeline:

1. **Ingestion**: reads your source documents from S3, splits them into chunks, calls an embedding model (Amazon Titan Embed Text v2) to convert each chunk into a 1024-dimensional vector, and stores those vectors in Aurora.
2. **Retrieval**: when the agent calls `retrieve("Italian restaurants")`, Bedrock embeds that query and finds the chunks in Aurora whose vectors are closest to it — semantically similar content, not just keyword matches.

You get this entire pipeline by defining two resources: a Knowledge Base and a data source. Bedrock handles everything in between.

### The IAM role — Bedrock's identity in your account

Bedrock's Knowledge Base service does not run inside your AWS account. It runs in AWS's managed service plane and assumes a role in your account to act on your resources. We create that role explicitly so we control exactly what it can do.

```typescript
// infra/ai.ts

const kbExecutionRole = new aws.iam.Role("KbExecutionRole", {
  assumeRolePolicy: {
    Version: "2012-10-17",
    Statement: [{
      Effect: "Allow",
      Principal: { Service: "bedrock.amazonaws.com" },
      Action: "sts:AssumeRole",
      Condition: {
        // Prevents Bedrock in any other AWS account from assuming this role
        StringEquals: { "aws:SourceAccount": aws.getCallerIdentityOutput().accountId },
      },
    }],
  },
  inlinePolicies: [
    {
      // Bedrock calls Titan Embed to convert document chunks into vectors during ingestion
      name: "KnowledgeBaseFoundationModelPolicy",
      policy: aws.getRegionOutput().name.apply((region) => JSON.stringify({
        Version: "2012-10-17",
        Statement: [{
          Effect: "Allow",
          Action: ["bedrock:InvokeModel"],
          Resource: [`arn:aws:bedrock:${region}::foundation-model/amazon.titan-embed-text-v2:0`],
        }],
      })),
    },
    {
      // Bedrock reads .docx files from the KB bucket during ingestion
      name: "KnowledgeBaseS3AccessPolicy",
      policy: $resolve(kbBucket.arn).apply((arn) => JSON.stringify({
        Version: "2012-10-17",
        Statement: [{
          Effect: "Allow",
          Action: ["s3:GetObject", "s3:ListBucket"],
          Resource: [arn, `${arn}/*`],
        }],
      })),
    },
    {
      // Bedrock uses the RDS Data API to write embeddings during ingestion and read them at query time
      name: "KnowledgeBaseRDSAccessPolicy",
      policy: $resolve([rds.clusterArn, rds.secretArn]).apply(([clusterArn, secretArn]) =>
        JSON.stringify({
          Version: "2012-10-17",
          Statement: [
            { Effect: "Allow", Action: ["rds:DescribeDBClusters"], Resource: [clusterArn] },
            { Effect: "Allow", Action: ["rds-data:BatchExecuteStatement", "rds-data:ExecuteStatement"], Resource: [clusterArn] },
            // The Data API authenticates using the cluster's Secrets Manager secret —
            // Bedrock retrieves the secret to get the database credentials
            { Effect: "Allow", Action: ["secretsmanager:GetSecretValue"], Resource: [secretArn] },
          ],
        }),
      ),
    },
  ],
});
```

Three policies, each scoped to the minimum:

- **Foundation model**: `bedrock:InvokeModel` on exactly the Titan Embed v2 ARN. Bedrock cannot use this role to invoke any other model.
- **S3**: `GetObject` + `ListBucket` on exactly the KB bucket. Bedrock cannot access any other bucket.
- **RDS**: `DescribeDBClusters` + Data API actions + `secretsmanager:GetSecretValue`, all scoped to exactly this cluster and its secret. `DescribeDBClusters` lets Bedrock verify the cluster is available before connecting; `GetSecretValue` is how the Data API authenticates — it reads the secret to get the database password rather than requiring you to pass credentials directly.

### The Knowledge Base resource

```typescript
const knowledgeBase = new aws.bedrock.AgentKnowledgeBase("RestaurantKB", {
  name: `${$app.name}-${$app.stage}`,
  roleArn: kbExecutionRole.arn,
  knowledgeBaseConfiguration: {
    type: "VECTOR",
    vectorKnowledgeBaseConfiguration: {
      embeddingModelArn: aws.getRegionOutput().name.apply(
        (region) => `arn:aws:bedrock:${region}::foundation-model/amazon.titan-embed-text-v2:0`,
      ),
    },
  },
  storageConfiguration: {
    type: "RDS",
    rdsConfiguration: {
      resourceArn: rds.clusterArn,
      databaseName: rds.database,
      tableName: "bedrock_integration.bedrock_kb",
      credentialsSecretArn: rds.secretArn,
      // These names must match the column names in init-db.sql exactly
      fieldMapping: {
        primaryKeyField: "id",
        vectorField: "embedding",
        textField: "chunks",
        metadataField: "metadata",
      },
    },
  },
}, { dependsOn: [kbExecutionRole, initSchema] });
```

**Why stage-aware naming (`${$app.name}-${$app.stage}`)?**

AWS resource names are global within an account for many services. If the KB name were hardcoded as `"restaurant-assistant"`, deploying a `staging` stage while `dev` exists would fail with a name conflict. Deriving names from `$app.name` and `$app.stage` gives each stage its own namespace automatically.

**Why `dependsOn: [kbExecutionRole, initSchema]`?**

Two things must be true before Bedrock can create the Knowledge Base:

1. The IAM role must exist so Bedrock can assume it immediately. Pulumi infers a dependency via the `roleArn` reference — but being explicit with `dependsOn` makes the intent clear.
2. The schema in Aurora must exist. Without the `bedrock_integration.bedrock_kb` table, Bedrock will attempt to validate the storage configuration and fail. `initSchema` is a local command — Pulumi cannot automatically infer the KB resource depends on it, so we declare it explicitly.

**The `fieldMapping` is a hard contract.**

The column names in `fieldMapping` must match the column names in `init-db.sql` exactly. `vectorField: "embedding"` means Bedrock will write to a column named `embedding`. If you change one without changing the other, ingestion fails silently or the KB creates a broken index. Treat this mapping as load-bearing configuration.

### Registering the KB with SST's link system

SST's `link` mechanism does two things: injects resource values into Lambda as environment variables at deploy time, and automatically grants the Lambda's execution role IAM permissions for those resources. SST knows how to do this for its own first-party resources (`sst.aws.Dynamo`, `sst.aws.Bucket`, etc.) but knows nothing about a raw Pulumi resource like `aws.bedrock.AgentKnowledgeBase`.

`Linkable.wrap()` bridges that gap:

```typescript
sst.Linkable.wrap(aws.bedrock.AgentKnowledgeBase, (kb) => ({
  properties: { id: kb.id, arn: kb.arn, name: kb.name },
  include: [
    sst.aws.permission({
      actions: ["bedrock:RetrieveAndGenerate", "bedrock:Retrieve"],
      resources: [kb.arn],
    }),
  ],
}));
```

After this call, writing `link: [knowledgeBase]` in `infra/api.ts` causes SST to inject `Resource.RestaurantKB.id` into the Lambda and automatically add `bedrock:Retrieve` and `bedrock:RetrieveAndGenerate` permissions on the KB ARN to the Lambda's execution role.

Without `Linkable.wrap()`, `link: [knowledgeBase]` would silently inject nothing and grant no permissions — the Lambda would fail at runtime with an IAM error on the first `retrieve()` call.

---

## Part 5 — Document Ingestion Pipeline

### The problem: a KB with no documents

After deploying the Knowledge Base, it exists in AWS but contains no embeddings. The `retrieve()` tool would return nothing. We need to get the `.docx` files from `kb-documents/` into S3 and tell Bedrock to process them.

This involves three steps:
1. Define an S3 data source on the KB (tells Bedrock where to find documents and how to chunk them)
2. Upload the documents to S3
3. Trigger a Bedrock ingestion job

We want all three to happen automatically as part of `sst deploy`.

### The S3 data source

```typescript
const kbDataSource = new aws.bedrock.AgentDataSource("KbDataSource", {
  knowledgeBaseId: knowledgeBase.id,
  name: `${$app.name}-${$app.stage}-s3`,
  dataSourceConfiguration: {
    type: "S3",
    s3Configuration: {
      bucketArn: $resolve(kbBucket.arn),
    },
  },
  vectorIngestionConfiguration: {
    chunkingConfiguration: {
      chunkingStrategy: "FIXED_SIZE",
      fixedSizeChunkingConfiguration: { maxTokens: 512, overlapPercentage: 20 },
    },
  },
});
```

The chunking configuration controls how Bedrock splits each document before embedding it. Each chunk becomes one row in the Aurora table — one embedding vector.

**Why 512 tokens with 20% overlap?**

Smaller chunks (128–256 tokens) give more precise retrieval but may miss context that spans a paragraph boundary. Larger chunks (1024+ tokens) keep more context together but reduce the signal-to-noise ratio of each embedding — the vector represents more concepts at once, making it harder to match a specific query.

512 tokens is a well-tested default for document retrieval. 20% overlap (~102 tokens) means neighboring chunks share some text. If a key phrase falls at the boundary between two chunks, it will appear in both — so a query targeting that phrase can retrieve context from either side of the break.

### Automating upload and ingestion as Pulumi commands

Uploading files and kicking off ingestion are operational steps, not infrastructure resources. But they belong in the deployment graph for the same reason schema initialization does: you want `sst deploy` to leave the system in a fully working state, not require manual follow-up steps.

```typescript
// Upload kb-documents/ to S3 on every deploy.
// Note: the path is relative to .sst/platform/ (SST's Pulumi CWD), so ../../ reaches the project root.
const syncDocs = new command.local.Command(
  "SyncKbDocs",
  {
    create: $interpolate`aws s3 sync ../../kb-documents/ s3://${kbBucket.name}/ --profile iamadmin-general --region us-east-1`,
  },
  { dependsOn: [kbDataSource] },
);

// Start a Bedrock ingestion job after documents are in S3.
new command.local.Command(
  "StartIngestion",
  {
    create: $interpolate`aws bedrock-agent start-ingestion-job --knowledge-base-id ${knowledgeBase.id} --data-source-id ${kbDataSource.dataSourceId} --profile iamadmin-general --region us-east-1`,
  },
  { dependsOn: [syncDocs] },
);
```

**Why chain `SyncKbDocs → StartIngestion` rather than run them in parallel?**

The ingestion job reads documents from S3. If `StartIngestion` runs before `SyncKbDocs` finishes uploading, the job starts with an empty or incomplete bucket and completes immediately with no documents processed — silently. The `dependsOn: [syncDocs]` dependency ensures the ingestion job only starts once all files are in the bucket.

**Why `../../kb-documents/`?**

SST runs Pulumi from `.sst/platform/` inside the project root. All relative paths in Pulumi commands are resolved relative to that directory. `../../` navigates back to the project root where `kb-documents/` lives. This is a gotcha worth knowing: if a Pulumi command path ever resolves to the wrong place, check whether it's relative to the project root or to `.sst/platform/`.

**Why is `s3 sync` safe to run on every deploy?**

`aws s3 sync` is idempotent — it compares the local files and the S3 bucket and only uploads files that have changed. The same applies to the ingestion job: Bedrock tracks which document versions have been ingested and skips unchanged files. Re-deploying does not re-embed documents that have not changed.

Deploy again:

```bash
npx sst deploy --stage dev
```

Pulumi will: create the data source, sync `kb-documents/` to S3, then start the ingestion job. The ingestion job runs asynchronously in AWS — it may take a few minutes to complete. You can check its status in the AWS Console under Bedrock → Knowledge Bases → your KB → Data source → Sync history.

### Testing the Knowledge Base: `scripts/test-kb.ts`

Once ingestion completes, verify the KB is returning results before wiring it to the agent.

The test script has two modes that test different layers of the RAG pipeline:

```bash
# Mode 1: raw vector retrieval — tests whether documents were indexed correctly
bun sst shell --stage dev -- bun run scripts/test-kb.ts retrieve "What Italian restaurants are available?"

# Mode 2: full RAG pipeline — tests retrieval + LLM synthesis together
bun sst shell --stage dev -- bun run scripts/test-kb.ts generate "What Italian restaurants are available?"
```

**`retrieve` mode** calls the vector store directly and returns the top-N chunks whose embeddings are closest to the query. No LLM is involved. Use this to debug whether ingestion is working — if you get results, documents were chunked and embedded correctly.

One thing to know about vector search: it is *semantic*, not keyword matching. A query for "Italian restaurants" may return chunks about French or Japanese restaurants, because all restaurant menus share vocabulary (dishes, ingredients, prices, atmosphere) and score similarly in embedding space. This is expected behavior, not a bug. The LLM's job in `generate` mode is to reason over the retrieved chunks and filter them.

**`generate` mode** runs the full pipeline: it retrieves chunks, passes them to Claude Haiku as context, and returns a synthesized answer. If `retrieve` returns plausible chunks but `generate` returns a wrong or incomplete answer, the issue is in how the LLM is reasoning over the context — not in the indexing. The two modes let you isolate which layer of the pipeline to debug.

We use Claude Haiku for this test script (not Sonnet) because we are only validating that retrieval works, not evaluating reasoning quality. Haiku is faster and cheaper for ad-hoc verification.

---

## Part 6 — API Gateway and Lambda

With the storage layer and knowledge base in place, we can deploy the application itself.

```typescript
// infra/api.ts

const api = new sst.aws.ApiGatewayV2("RestaurantApi", {
  cors: {
    allowOrigins: ["*"],   // TODO: restrict to the Vercel domain once known
    allowMethods: ["GET", "POST", "DELETE"],
    allowHeaders: ["*"],
  },
});

// POST /chat — sized for a multi-turn Bedrock agent with multiple tool calls
api.route("POST /chat", {
  handler: "backend/app/handler_chat.handler",
  runtime: "python3.11",
  timeout: "120 seconds",
  memory: "1024 MB",
  link: [table, knowledgeBase],
  permissions: [{
    actions: ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
    resources: ["arn:aws:bedrock:*::foundation-model/anthropic.claude-3-7-sonnet-*"],
  }],
});

// GET /bookings/{id} and DELETE /bookings/{id} — simple DynamoDB reads, no Bedrock access
api.route("GET /bookings/{id}", {
  handler: "backend/app/handler_bookings.handler",
  runtime: "python3.11",
  timeout: "10 seconds",
  memory: "256 MB",
  link: [table],
});

api.route("DELETE /bookings/{id}", {
  handler: "backend/app/handler_bookings.handler",
  runtime: "python3.11",
  timeout: "10 seconds",
  memory: "256 MB",
  link: [table],
});

export const url = api.url;
```

### Why two separate Lambda functions?

The `/chat` route runs a Strands agent that may call Claude multiple times, query the Knowledge Base, and hit DynamoDB — all in a single user request. A single agent turn can take 30–60 seconds and needs the full Python runtime with Strands, boto3, and all Bedrock dependencies loaded.

The `/bookings` routes are simple DynamoDB reads and deletes. They finish in under a second and do not touch Bedrock at all.

If both routes shared a single Lambda, every DynamoDB lookup would pay the cold-start overhead of loading the entire Strands agent stack. Separate functions mean each is sized exactly for its workload: 120 seconds and 1024 MB for the agent, 10 seconds and 256 MB for CRUD. The bookings function also stays warm independently — a busy agent handler will not starve the bookings handler of concurrency.

### What `link: [table, knowledgeBase]` does

SST's `link` system handles two things automatically when you add a resource to the `link` array:

1. **Injects the resource's values** into the Lambda as environment variables at deploy time. The chat handler can then do `from sst import Resource; kb_id = Resource.RestaurantKB.id` — no SSM calls, no hardcoded ARNs.
2. **Grants IAM permissions**. Linking `table` grants the Lambda's execution role DynamoDB read/write permissions on that specific table. Linking `knowledgeBase` triggers the `Linkable.wrap()` definition we set up earlier, granting `bedrock:Retrieve` and `bedrock:RetrieveAndGenerate` on the KB ARN.

The explicit `permissions` block for `bedrock:InvokeModel` covers the Strands agent's LLM calls — invoking Claude directly. This permission is not granted by linking the KB, because the KB is a retrieval resource, not an inference resource.

---

## Full Deployment Graph

Here is the complete order of operations when you run `sst deploy --stage dev` with all modules enabled:

```
sst deploy --stage dev
  │
  ├── infra/networking.ts
  │   └── VPC + bastion host
  │
  ├── infra/storage.ts
  │   ├── S3 bucket (KbDocuments)
  │   ├── Aurora cluster + instance (VectorStore)
  │   └── DynamoDB table (Bookings) + GSIs
  │
  └── infra/ai.ts
      ├── KbExecutionRole         [IAM role for Bedrock service plane]
      ├── InitDbSchema            [waits for: Aurora instance]
      │     → runs 6 SQL statements via RDS Data API
      │       creates: vector extension, bedrock_integration schema,
      │                bedrock_kb table, HNSW index, 2× GIN indexes
      ├── RestaurantKB            [waits for: KbExecutionRole + InitDbSchema]
      ├── KbDataSource            [waits for: RestaurantKB]
      ├── SyncKbDocs              [waits for: KbDataSource]
      │     → aws s3 sync kb-documents/ → S3
      └── StartIngestion          [waits for: SyncKbDocs]
            → aws bedrock-agent start-ingestion-job
              Bedrock reads S3, chunks docs, calls Titan Embed,
              writes vectors to Aurora bedrock_kb table
```

Every step in this graph is either a tracked AWS resource or an idempotent local command. `sst deploy` is the only command needed to go from a blank AWS account to a fully populated knowledge base.
