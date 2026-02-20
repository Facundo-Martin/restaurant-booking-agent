import { ossVpcEndpoint } from "./networking";
import { kbBucket } from "./storage";

// Stage-aware name used across all OpenSearch Serverless (OSS) resources to avoid conflicts between stages
const collectionName = `${$app.name}-${$app.stage}`;

// Encryption policy (must exist before the collection is created) -> https://www.pulumi.com/registry/packages/aws/api-docs/opensearch/serverlesscollection/
const ossEncryptionPolicy = new aws.opensearch.ServerlessSecurityPolicy(
  "OssEncryption",
  {
    name: `${collectionName}-enc`,
    type: "encryption",
    policy: JSON.stringify({
      Rules: [
        {
          Resource: [`collection/${collectionName}`],
          ResourceType: "collection",
        },
      ],
      AWSOwnedKey: true,
    }),
  },
);

// Vector store that holds the restaurant document embeddings used for RAG retrieval
const ossCollection = new aws.opensearch.ServerlessCollection(
  "OssCollection",
  {
    name: collectionName,
    type: "VECTORSEARCH",
  },
  { dependsOn: [ossEncryptionPolicy] },
);

// Blocks all public internet access — only traffic through the OSS VPC endpoint is accepted
new aws.opensearch.ServerlessSecurityPolicy("OssNetwork", {
  name: `${collectionName}-net`,
  type: "network",
  policy: ossVpcEndpoint.id.apply((vpceId) =>
    JSON.stringify([
      {
        Rules: [
          {
            Resource: [`collection/${collectionName}`],
            ResourceType: "collection",
          },
        ],
        AllowFromPublic: false,
        SourceVPCEs: [vpceId],
      },
    ]),
  ),
});

// IAM role that Bedrock assumes to read documents from S3 and write embeddings to OSS
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
      name: "KbFmPolicy",
      policy: aws.getRegionOutput().name.apply((region) =>
        JSON.stringify({
          Version: "2012-10-17",
          Statement: [
            {
              Effect: "Allow",
              Action: ["bedrock:InvokeModel"],
              Resource: `arn:aws:bedrock:${region}::foundation-model/amazon.titan-embed-text-v2:0`,
            },
          ],
        }),
      ),
    },
    {
      // Allows Bedrock to read .docx source files from the KB bucket during ingestion
      name: "KbS3Policy",
      policy: $resolve(kbBucket.arn).apply((arn) =>
        JSON.stringify({
          Version: "2012-10-17",
          Statement: [
            {
              Effect: "Allow",
              Action: ["s3:GetObject", "s3:ListBucket"],
              Resource: [arn, `${arn}/*`],
            },
          ],
        }),
      ),
    },
    {
      // Allows Bedrock to write embeddings into the OSS collection
      // aoss:APIAccessAll is the only IAM-level OSS action — fine-grained control lives in OssDataAccess below
      name: "KbOssPolicy",
      policy: ossCollection.arn.apply((arn) =>
        JSON.stringify({
          Version: "2012-10-17",
          Statement: [
            {
              Effect: "Allow",
              Action: ["aoss:APIAccessAll"],
              Resource: arn,
            },
          ],
        }),
      ),
    },
  ],
});

// Grants the KB execution role (ingestion pipeline) and the deployer (debugging) access to the collection
new aws.opensearch.ServerlessAccessPolicy("OssDataAccess", {
  name: `${collectionName}-data`,
  type: "data",
  policy: kbExecutionRole.arn.apply((roleArn) =>
    aws.getCallerIdentityOutput().arn.apply((deployerArn) =>
      JSON.stringify([
        {
          Rules: [
            {
              ResourceType: "collection",
              Resource: [`collection/${collectionName}`],
              Permission: [
                "aoss:CreateCollectionItems",
                "aoss:DeleteCollectionItems",
                "aoss:UpdateCollectionItems",
                "aoss:DescribeCollectionItems",
              ],
            },
            {
              ResourceType: "index",
              Resource: [`index/${collectionName}/*`],
              Permission: [
                "aoss:CreateIndex",
                "aoss:DeleteIndex",
                "aoss:UpdateIndex",
                "aoss:DescribeIndex",
                "aoss:ReadDocument",
                "aoss:WriteDocument",
              ],
            },
          ],
          Principal: [roleArn, deployerArn],
        },
      ]),
    ),
  ),
});

// Bedrock Knowledge Base — wires together the OSS vector store, the embedding model, and the S3 data source
const knowledgeBase = new aws.bedrock.AgentKnowledgeBase(
  "RestaurantKB",
  {
    name: collectionName,
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
      type: "OPENSEARCH_SERVERLESS",
      opensearchServerlessConfiguration: {
        collectionArn: ossCollection.arn,
        vectorIndexName: `${collectionName}-index`,
        fieldMapping: {
          vectorField: "vector",
          textField: "text",
          metadataField: "text-metadata",
        },
      },
    },
  },
  { dependsOn: [kbExecutionRole, ossCollection] },
);

// S3 data source — tells Bedrock where to find documents and how to chunk them before embedding
new aws.bedrock.AgentDataSource("KbDataSource", {
  knowledgeBaseId: knowledgeBase.id,
  name: `${collectionName}-s3`,
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

// TODO: Trigger a KB ingestion job after the data source is created
// The Pulumi AWS provider has no native ingestion job resource — needs a custom script or SDK call post-deploy

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
