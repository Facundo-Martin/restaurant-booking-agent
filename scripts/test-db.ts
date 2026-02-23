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
  RDSClient,
  DescribeDBClustersCommand,
  type DBCluster,
} from "@aws-sdk/client-rds";
import {
  RDSDataClient,
  ExecuteStatementCommand,
} from "@aws-sdk/client-rds-data";
import { Resource } from "sst";

const REGION = "us-east-1";

// Resource.VectorStore is the sst.aws.Aurora component named "VectorStore" in infra/storage.ts
// @ts-ignore — injected by sst shell at runtime
const host: string = Resource.VectorStore.host;
// @ts-ignore
const database: string = Resource.VectorStore.database;

// Discover cluster ARN and managed secret ARN by matching the endpoint
const rdsClient = new RDSClient({ region: REGION });
// @ts-ignore — top-level await, valid at runtime with bun
const { DBClusters } = await rdsClient.send(new DescribeDBClustersCommand({}));

const cluster = DBClusters?.find((c: DBCluster) => c.Endpoint === host);
if (!cluster?.DBClusterArn) {
  console.error(`No Aurora cluster found with endpoint: ${host}`);
  console.error("Is the stack deployed? Run: npx sst deploy --stage <stage>");
  process.exit(1);
}

const clusterArn = cluster.DBClusterArn;
const secretArn = cluster.MasterUserSecret?.SecretArn;
if (!secretArn) {
  console.error("Cluster has no managed secret — check SST Aurora config.");
  process.exit(1);
}

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

// @ts-ignore — top-level await
const results = await Promise.all([
  check(
    "vector extension",
    "SELECT extname FROM pg_extension WHERE extname = 'vector'",
    "vector",
  ),
  check(
    "bedrock_integration schema",
    "SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'bedrock_integration'",
    "bedrock_integration",
  ),
  check(
    "bedrock_kb table",
    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'bedrock_integration' AND table_name = 'bedrock_kb'",
    "bedrock_kb",
  ),
  check(
    "hnsw embedding index (bedrock_kb_embedding_idx)",
    "SELECT indexname FROM pg_indexes WHERE tablename = 'bedrock_kb' AND indexname = 'bedrock_kb_embedding_idx'",
    "bedrock_kb_embedding_idx",
  ),
  check(
    "gin chunks index (bedrock_kb_chunks_idx)",
    "SELECT indexname FROM pg_indexes WHERE tablename = 'bedrock_kb' AND indexname = 'bedrock_kb_chunks_idx'",
    "bedrock_kb_chunks_idx",
  ),
  check(
    "gin metadata index (bedrock_kb_custom_metadata_idx)",
    "SELECT indexname FROM pg_indexes WHERE tablename = 'bedrock_kb' AND indexname = 'bedrock_kb_custom_metadata_idx'",
    "bedrock_kb_custom_metadata_idx",
  ),
]);

const passed = results.filter(Boolean).length;
console.log(`\n${passed}/${results.length} checks passed`);
if (passed < results.length) process.exit(1);
