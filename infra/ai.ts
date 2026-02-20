import { kbBucket } from "./storage";

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
    // TODO: Add KbRdsPolicy once Aurora cluster is provisioned in infra/database.ts
  ],
});

export { kbExecutionRole };

// TODO: Provision Bedrock Knowledge Base backed by Aurora RDS (pgvector) once infra/database.ts is ready.
// Steps:
//   1. Add the Aurora cluster ARN and secret ARN to KbExecutionRole via a KbRdsPolicy inline policy
//   2. Create aws.bedrock.AgentKnowledgeBase with storageConfiguration.type = "RDS"
//   3. Create aws.bedrock.AgentDataSource pointing at kbBucket
//   4. Register the KB with sst.Linkable.wrap() so Lambda functions receive its ID via link:
