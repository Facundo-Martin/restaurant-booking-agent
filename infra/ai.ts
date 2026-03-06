import * as command from "@pulumi/command";
import { rds, kbBucket } from "./storage";

// IAM role that Bedrock assumes to read documents from S3 and write embeddings to the vector store
const kbExecutionRole = new aws.iam.Role("KbExecutionRole", {
  assumeRolePolicy: {
    Version: "2012-10-17",
    Statement: [
      {
        Effect: "Allow",
        Principal: { Service: "bedrock.amazonaws.com" },
        Action: "sts:AssumeRole",
        Condition: {
          StringEquals: {
            "aws:SourceAccount": aws.getCallerIdentityOutput().accountId,
          },
        },
      },
    ],
  },
  inlinePolicies: [
    {
      // Allows Bedrock to call the Titan embedding model when ingesting documents
      name: "KnowledgeBaseFoundationModelPolicy",
      policy: aws.getRegionOutput().name.apply((region) =>
        JSON.stringify({
          Version: "2012-10-17",
          Statement: [
            {
              Sid: "BedrockInvokeEmbeddingModel",
              Effect: "Allow",
              Action: ["bedrock:InvokeModel"],
              Resource: [
                `arn:aws:bedrock:${region}::foundation-model/amazon.titan-embed-text-v2:0`,
              ],
            },
          ],
        }),
      ),
    },
    {
      // Allows Bedrock to read .docx source files from the KB bucket during ingestion
      name: "KnowledgeBaseS3AccessPolicy",
      policy: $resolve(kbBucket.arn).apply((arn) =>
        JSON.stringify({
          Version: "2012-10-17",
          Statement: [
            {
              Sid: "S3ReadSourceDocuments",
              Effect: "Allow",
              Action: ["s3:GetObject", "s3:ListBucket"],
              Resource: [arn, `${arn}/*`],
            },
          ],
        }),
      ),
    },
    {
      // Allows Bedrock to query Aurora via the RDS Data API and read the credentials secret
      name: "KnowledgeBaseRDSAccessPolicy",
      policy: $resolve([rds.clusterArn, rds.secretArn]).apply(
        ([clusterArn, secretArn]) =>
          JSON.stringify({
            Version: "2012-10-17",
            Statement: [
              {
                Sid: "RDSDescribe",
                Effect: "Allow",
                Action: ["rds:DescribeDBClusters"],
                Resource: [clusterArn],
              },
              {
                Sid: "RDSDataApiAccess",
                Effect: "Allow",
                Action: [
                  "rds-data:BatchExecuteStatement",
                  "rds-data:ExecuteStatement",
                ],
                Resource: [clusterArn],
              },
              {
                Sid: "SecretsManagerAccess",
                Effect: "Allow",
                Action: ["secretsmanager:GetSecretValue"],
                Resource: [secretArn],
              },
            ],
          }),
      ),
    },
  ],
});

// Initialize pgvector schema in Aurora via the RDS Data API — no tunnel or bastion needed.
// Data API is accessible directly from the deployer's machine with IAM credentials.
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
          exec(
            "CREATE TABLE IF NOT EXISTS bedrock_integration.bedrock_kb (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), embedding vector(1024), chunks text NOT NULL, metadata json NOT NULL, custom_metadata jsonb)",
          ),
          exec(
            "CREATE INDEX IF NOT EXISTS bedrock_kb_embedding_idx ON bedrock_integration.bedrock_kb USING hnsw (embedding vector_cosine_ops) WITH (ef_construction=256)",
          ),
          exec(
            "CREATE INDEX IF NOT EXISTS bedrock_kb_chunks_idx ON bedrock_integration.bedrock_kb USING gin (to_tsvector('simple', chunks))",
          ),
          exec(
            "CREATE INDEX IF NOT EXISTS bedrock_kb_custom_metadata_idx ON bedrock_integration.bedrock_kb USING gin (custom_metadata)",
          ),
        ].join(" &&\n");
      },
    ),
  },
  // The RDS Data API requires a running cluster *instance*, not just the cluster itself.
  // dependsOn ensures Pulumi waits for the instance to finish provisioning before
  // attempting any SQL via the Data API.
  { dependsOn: [rds.nodes.instance] },
);

// Bedrock Knowledge Base — backed by Aurora + pgvector instead of OSS
const knowledgeBase = new aws.bedrock.AgentKnowledgeBase(
  "RestaurantKB",
  {
    name: `${$app.name}-${$app.stage}`,
    roleArn: kbExecutionRole.arn,
    knowledgeBaseConfiguration: {
      type: "VECTOR",
      vectorKnowledgeBaseConfiguration: {
        embeddingModelArn: aws
          .getRegionOutput()
          .name.apply(
            (region) =>
              `arn:aws:bedrock:${region}::foundation-model/amazon.titan-embed-text-v2:0`,
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
        fieldMapping: {
          primaryKeyField: "id",
          vectorField: "embedding",
          textField: "chunks",
          metadataField: "metadata",
        },
      },
    },
  },
  { dependsOn: [kbExecutionRole, initSchema] },
);

// S3 data source — tells Bedrock where to find documents and how to chunk them before embedding
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

// Registers the KB with SST's link system so Lambda functions receive its ID at deploy time
// and are automatically granted bedrock:Retrieve + bedrock:RetrieveAndGenerate permissions
sst.Linkable.wrap(aws.bedrock.AgentKnowledgeBase, (kb) => ({
  properties: { id: kb.id, arn: kb.arn, name: kb.name },
  include: [
    sst.aws.permission({
      actions: ["bedrock:RetrieveAndGenerate", "bedrock:Retrieve"],
      resources: [kb.arn],
    }),
  ],
}));

// Bedrock Guardrail — enforces topic boundaries, blocks harmful content, and anonymises PII
// before it reaches the model or appears in responses. Evaluated on every model invocation.
// When triggered, Strands sets stop_reason="guardrail_intervened" and overwrites the
// offending message in conversation history; the existing force_stop handler in chat.py covers it.
const guardrail = new aws.bedrock.Guardrail("RestaurantGuardrail", {
  name: `${$app.name}-${$app.stage}`,
  blockedInputMessaging: "I can only help with restaurant discovery and bookings.",
  blockedOutputsMessaging: "I can only help with restaurant discovery and bookings.",
  topicPolicyConfig: {
    topicsConfigs: [
      {
        name: "off-topic",
        definition: "Any topic unrelated to restaurant discovery, menus, or table reservations.",
        type: "DENY",
      },
    ],
  },
  contentPolicyConfig: {
    filtersConfigs: [
      { type: "HATE", inputStrength: "HIGH", outputStrength: "HIGH" },
      { type: "VIOLENCE", inputStrength: "HIGH", outputStrength: "HIGH" },
      { type: "PROMPT_ATTACK", inputStrength: "HIGH", outputStrength: "NONE" },
    ],
  },
  sensitiveInformationPolicyConfig: {
    piiEntitiesConfigs: [
      { type: "EMAIL", action: "ANONYMIZE" },
      { type: "PHONE", action: "ANONYMIZE" },
      { type: "CREDIT_DEBIT_CARD_NUMBER", action: "BLOCK" },
    ],
  },
  // AWS managed profanity list — blocks profane words in both inputs and outputs
  wordPolicyConfig: {
    managedWordListsConfigs: [{ type: "PROFANITY" }],
  },
});

// Register with SST link so guardrailId + version are injected into the chat Lambda at deploy time
sst.Linkable.wrap(aws.bedrock.Guardrail, (g) => ({
  properties: { id: g.guardrailId, version: g.version },
}));

// Upload kb-documents/ to S3 on every deploy, then kick off a Bedrock ingestion job.
// Note: Path is relative to .sst/platform/ (SST's Pulumi CWD), so ../../ reaches the project root.
const syncDocs = new command.local.Command(
  "SyncKbDocs",
  {
    create: $interpolate`aws s3 sync ../../kb-documents/ s3://${kbBucket.name}/ --profile iamadmin-general --region us-east-1`,
  },
  { dependsOn: [kbDataSource] },
);

new command.local.Command(
  "StartIngestion",
  {
    create: $interpolate`aws bedrock-agent start-ingestion-job --knowledge-base-id ${knowledgeBase.id} --data-source-id ${kbDataSource.dataSourceId} --profile iamadmin-general --region us-east-1`,
  },
  { dependsOn: [syncDocs] },
);

export { knowledgeBase, guardrail };
