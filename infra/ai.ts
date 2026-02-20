import { aurora, kbBucket } from "./storage";

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
              Resource: [`arn:aws:bedrock:${region}::foundation-model/amazon.titan-embed-text-v2:0`],
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
      policy: $resolve([aurora.clusterArn, aurora.secretArn]).apply(
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

// Bedrock Knowledge Base — backed by Aurora + pgvector instead of OSS
// Aurora must already have the pgvector schema applied (see scripts/init-db.sql) before this deploys
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
        resourceArn: aurora.clusterArn,
        databaseName: "postgres",
        tableName: "bedrock_integration.bedrock_kb",
        credentialsSecretArn: aurora.secretArn,
        fieldMapping: {
          primaryKeyField: "id",
          vectorField: "embedding",
          textField: "chunks",
          metadataField: "metadata",
        },
      },
    },
  },
  { dependsOn: [kbExecutionRole] },
);

// S3 data source — tells Bedrock where to find documents and how to chunk them before embedding
new aws.bedrock.AgentDataSource("KbDataSource", {
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
      actions: ["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"],
      resources: [kb.arn],
    }),
  ],
}));

export { knowledgeBase };
