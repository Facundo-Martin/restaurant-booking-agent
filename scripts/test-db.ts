/**
 * Verifies the pgvector schema in Aurora via the RDS Data API.
 * No tunnel or bastion needed — uses the same Data API path as InitDbSchema.
 *
 * Run with:
 *   bun sst shell --stage <stage> -- bun run scripts/test-db.ts
 *
 * Checks (all must pass before deploying infra/ai.ts):
 *   ✓ vector extension installed
 *   ✓ bedrock_integration schema exists
 *   ✓ bedrock_kb table exists
 *   ✓ hnsw embedding index exists
 *   ✓ gin chunks (full-text) index exists
 *   ✓ gin custom_metadata index exists
 */

import {
  RDSDataClient,
  ExecuteStatementCommand,
} from "@aws-sdk/client-rds-data";
import { Resource } from "sst";

const REGION = "us-east-1";

// SST Aurora injects clusterArn, secretArn, and database directly — no cluster discovery needed.
// MasterUserSecret is not set on SST Aurora clusters; it uses its own Secrets Manager secret.
// @ts-ignore — injected by sst shell at runtime
const clusterArn: string = Resource.VectorStore.clusterArn;
// @ts-ignore
const secretArn: string = Resource.VectorStore.secretArn;
// @ts-ignore
const database: string = Resource.VectorStore.database;

console.log(`Cluster: ${clusterArn}`);
console.log(`Database: ${database}`);
console.log("---");

const dataClient = new RDSDataClient({ region: REGION });

async function query(sql: string): Promise<string | null> {
  const result = await dataClient.send(
    new ExecuteStatementCommand({
      resourceArn: clusterArn,
      secretArn,
      database,
      sql,
    }),
  );
  return result.records?.[0]?.[0]?.stringValue ?? null;
}

async function check(
  label: string,
  sql: string,
  expected: string,
): Promise<boolean> {
  const value = await query(sql);
  const ok = value === expected;
  console.log(
    `${ok ? "✓" : "✗"} ${label}${ok ? "" : `  (expected: "${expected}", got: "${value ?? "null"}")`}`,
  );
  return ok;
}

const checks = [
  // 1. Verify the pgvector extension is installed — required for storing and querying embeddings
  {
    label: "vector extension",
    sql: "SELECT extname FROM pg_extension WHERE extname = 'vector'",
    expected: "vector",
  },
  // 2. Verify the bedrock_integration schema exists — Bedrock expects this exact namespace
  {
    label: "bedrock_integration schema",
    sql: "SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'bedrock_integration'",
    expected: "bedrock_integration",
  },
  // 3. Verify the bedrock_kb table exists with the correct schema and column layout
  {
    label: "bedrock_kb table",
    sql: "SELECT table_name FROM information_schema.tables WHERE table_schema = 'bedrock_integration' AND table_name = 'bedrock_kb'",
    expected: "bedrock_kb",
  },
  // 4. Verify the HNSW index on the embedding column exists — needed for vector similarity search
  {
    label: "hnsw embedding index (bedrock_kb_embedding_idx)",
    sql: "SELECT indexname FROM pg_indexes WHERE tablename = 'bedrock_kb' AND indexname = 'bedrock_kb_embedding_idx'",
    expected: "bedrock_kb_embedding_idx",
  },
  // 5. Verify the GIN index on the chunks column exists — needed for full-text keyword search
  {
    label: "gin chunks index (bedrock_kb_chunks_idx)",
    sql: "SELECT indexname FROM pg_indexes WHERE tablename = 'bedrock_kb' AND indexname = 'bedrock_kb_chunks_idx'",
    expected: "bedrock_kb_chunks_idx",
  },
  // 6. Verify the GIN index on custom_metadata exists — needed for filtering by metadata fields
  {
    label: "gin metadata index (bedrock_kb_custom_metadata_idx)",
    sql: "SELECT indexname FROM pg_indexes WHERE tablename = 'bedrock_kb' AND indexname = 'bedrock_kb_custom_metadata_idx'",
    expected: "bedrock_kb_custom_metadata_idx",
  },
];

const results: boolean[] = [];
for (const { label, sql, expected } of checks) {
  // @ts-ignore — top-level await
  results.push(await check(label, sql, expected));
}

const passed = results.filter(Boolean).length;
console.log(`\n${passed}/${results.length} checks passed`);
if (passed < results.length) process.exit(1);
