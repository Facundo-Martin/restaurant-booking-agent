# Migration Plan: OpenSearch Serverless → Aurora Serverless v2 + pgvector

## Why

OSS VECTORSEARCH collections require a minimum of 2 indexing OCUs + 2 search OCUs = **~$345/month** even at zero traffic.
Aurora Serverless v2 at 0.5 ACU minimum = **~$22/month** compute + ~$0.10/GB-month storage.

The only reason we previously kept OSS was to avoid operational complexity. This plan addresses that directly.

---

## What Changes

### `infra/networking.ts`
- Remove: `ossEndpointSg`, `ossVpcEndpoint` (OSS-specific resources)
- Keep: VPC — Aurora lives in private subnets too, same VPC works
- Add: `bastion: true` on the VPC — needed to SSH in and initialize the pgvector schema on first deploy
- Rename: `ossVpc` → `vpc` since the VPC is now general-purpose

### `infra/storage.ts`
- Add: `sst.aws.Aurora` cluster with `dataApi: true` (required by Bedrock), `engine: "postgres"`, `scaling: { min: "0.5 ACU", max: "4 ACU" }`
- Aurora creates a Secrets Manager secret automatically — export it alongside the cluster

### `infra/ai.ts`
- Remove: all OSS resources (encryption policy, collection, network policy, data access policy, `KbOssPolicy` on the IAM role)
- Remove: `import { ossVpcEndpoint }` — no longer needed
- Simplify IAM role: remove `KbOssPolicy`, add `rds-data:ExecuteStatement`, `rds-data:BatchExecuteStatement` on the cluster ARN + `secretsmanager:GetSecretValue` on the secret ARN
- Update KB `storageConfiguration`: change from `OPENSEARCH_SERVERLESS` to `RDS` with Aurora cluster ARN, secret ARN, and field mapping

### Schema initialization (new: `infra/db-init.ts` or a `scripts/init-db.sql`)
Aurora does not auto-create the schema like OSS does. The pgvector extension, schema, and table must be created manually before the KB can be deployed. Two options — see decision below.

---

## Aurora Cluster Config

```typescript
const aurora = new sst.aws.Aurora("RestaurantKB", {
  dataApi: true,      // Required by Bedrock — enables SQL over HTTPS without direct DB connection
  engine: "postgres",
  vpc,
  scaling: { min: "0.5 ACU", max: "4 ACU" },
});
```

---

## pgvector Schema

Must be executed once before `sst deploy` (or automated — see below):

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS bedrock_integration;

CREATE TABLE bedrock_integration.bedrock_kb (
  id        uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
  embedding vector(1024),   -- 1024 dims for Amazon Titan Embed Text v2
  chunks    text    NOT NULL,
  metadata  json    NOT NULL
);

-- HNSW index for fast approximate nearest-neighbour search
CREATE INDEX ON bedrock_integration.bedrock_kb
  USING hnsw (embedding vector_cosine_ops);
```

Column names map 1:1 to the KB field mapping:
```typescript
fieldMapping: {
  primaryKeyField: "id",
  vectorField:     "embedding",
  textField:       "chunks",
  metadataField:   "metadata",
}
```

---

## Schema Initialization — Decision Required

### Option A: Bastion host (manual, simplest)
Add `bastion: true` to the VPC. After `sst deploy`, SST provides a tunnel command:
```bash
npx sst tunnel --stage dev
psql -h <AURORA_ENDPOINT> -U postgres -d postgres < scripts/init-db.sql
```
Pros: simple, no extra resources. Cons: manual step on every new stage/account.

### Option B: Lambda init script (automated, recommended)
Deploy a one-shot Lambda that runs the SQL via the RDS Data API during `sst deploy`. Pulumi triggers it as a custom resource after the Aurora cluster is ready.
Pros: fully automated, no bastion needed. Cons: adds ~30 lines of infra code.

**Recommendation: Option B** — eliminates the manual step and makes the deployment self-contained.

---

## Updated KB `storageConfiguration`

```typescript
storageConfiguration: {
  type: "RDS",
  rdsConfiguration: {
    resourceArn:           aurora.clusterArn,
    databaseName:          "postgres",
    tableName:             "bedrock_integration.bedrock_kb",
    credentialsSecretArn:  aurora.nodes.cluster.masterUserSecrets[0].secretArn,
    fieldMapping: {
      primaryKeyField: "id",
      vectorField:     "embedding",
      textField:       "chunks",
      metadataField:   "metadata",
    },
  },
},
```

---

## Updated IAM Role Inline Policies

Remove `KbOssPolicy`. Add in its place:

```typescript
{
  name: "KbRdsPolicy",
  policy: aurora.clusterArn.apply((clusterArn) =>
    JSON.stringify({
      Version: "2012-10-17",
      Statement: [
        {
          Effect: "Allow",
          Action: ["rds:DescribeDBClusters", "rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement"],
          Resource: clusterArn,
        },
        {
          Effect: "Allow",
          Action: ["secretsmanager:GetSecretValue"],
          Resource: aurora.nodes.cluster.masterUserSecrets[0].secretArn,
        },
      ],
    }),
  ),
},
```

---

## Deployment Order (Updated)

```
1. sst deploy          → VPC + Aurora cluster + S3 bucket + DynamoDB table
2. [if Option A]       → SSH tunnel + psql < scripts/init-db.sql
   [if Option B]       → Lambda init runs automatically as part of step 1
3. sst deploy          → Bedrock KB (now finds the schema) + API Gateway
4. Upload .docx files  → trigger KB ingestion
```

---

## Files to Delete After Migration

- All OSS-specific Pulumi resources in `infra/ai.ts` (encryption policy, collection, network/data access policies)
- `ossVpcEndpoint` and `ossEndpointSg` in `infra/networking.ts`
- OSS-related todos and snippets in `infrastructure.md`

---

## Open Questions

1. **Schema init approach**: Option A (bastion) or Option B (Lambda)? Recommendation: B.
2. **Aurora cluster name**: reuse `${$app.name}-${$app.stage}` pattern for consistency.
3. **Max ACU**: 4 ACU fine for dev/staging. Increase to 16+ for production.
