-- pgvector schema initialization for Bedrock Knowledge Base (Aurora Serverless v2)
--
-- Run once per new stage/account before deploying the KB:
--   npx sst tunnel --stage <stage>
--   psql -h <AURORA_ENDPOINT> -U postgres -d postgres < scripts/init-db.sql
--
-- Column names map 1:1 to the fieldMapping in infra/ai.ts:
--   primaryKeyField: "id"
--   vectorField:     "embedding"
--   textField:       "chunks"
--   metadataField:   "metadata"

CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS bedrock_integration;

CREATE TABLE IF NOT EXISTS bedrock_integration.bedrock_kb (
  id              uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
  embedding       vector(1024),   -- 1024 dims for Amazon Titan Embed Text v2
  chunks          text    NOT NULL,
  metadata        json    NOT NULL,
  custom_metadata jsonb
);

-- HNSW index for fast approximate nearest-neighbour search (cosine distance)
-- ef_construction=256 improves recall at the cost of slightly longer index build time
CREATE INDEX IF NOT EXISTS bedrock_kb_embedding_idx
  ON bedrock_integration.bedrock_kb
  USING hnsw (embedding vector_cosine_ops) WITH (ef_construction=256);

-- GIN index for full-text search — Bedrock uses this for hybrid text queries
CREATE INDEX IF NOT EXISTS bedrock_kb_chunks_idx
  ON bedrock_integration.bedrock_kb
  USING gin (to_tsvector('simple', chunks));

-- GIN index for custom metadata filtering
CREATE INDEX IF NOT EXISTS bedrock_kb_custom_metadata_idx
  ON bedrock_integration.bedrock_kb
  USING gin (custom_metadata);
