/**
 * Tests the Bedrock Knowledge Base via the AWS SDK.
 * Requires the KB to be deployed (infra/ai.ts uncommented and deployed).
 *
 * Run with:
 *   bun sst shell --stage <stage> -- bun run scripts/test-kb.ts [mode] ["query"]
 *
 * Examples:
 *   bun sst shell --stage dev -- bun run scripts/test-kb.ts retrieve "What Italian restaurants are available?"
 *   bun sst shell --stage dev -- bun run scripts/test-kb.ts generate "What Italian restaurants are available?"
 */

import {
  BedrockAgentRuntimeClient,
  RetrieveCommand,
  RetrieveAndGenerateCommand,
} from "@aws-sdk/client-bedrock-agent-runtime";
import { Resource } from "sst";

const MODE = process.argv[2] ?? "retrieve";
const QUERY = process.argv[3] ?? "What restaurants are available?";
const REGION = "us-east-1";
const MODEL_ARN = `arn:aws:bedrock:${REGION}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0`;

const client = new BedrockAgentRuntimeClient({ region: REGION });

console.log(`Mode:  ${MODE}`);
console.log(`Query: ${QUERY}`);
console.log("---");

if (MODE === "retrieve") {
  // @ts-ignore -- top-level await, valid at runtime with bun
  const response = await client.send(
    new RetrieveCommand({
      knowledgeBaseId: Resource.RestaurantKB.id,
      retrievalQuery: { text: QUERY },
      retrievalConfiguration: {
        vectorSearchConfiguration: { numberOfResults: 5 },
      },
    }),
  );

  for (const result of response.retrievalResults ?? []) {
    console.log(`Score: ${result.score}`);
    console.log(`Text:  ${result.content?.text?.slice(0, 300)}`);
    console.log();
  }
} else if (MODE === "generate") {
  // @ts-ignore -- top-level await, valid at runtime with bun
  const response = await client.send(
    new RetrieveAndGenerateCommand({
      input: { text: QUERY },
      retrieveAndGenerateConfiguration: {
        type: "KNOWLEDGE_BASE",
        knowledgeBaseConfiguration: {
          knowledgeBaseId: Resource.RestaurantKB.id,
          modelArn: MODEL_ARN,
        },
      },
    }),
  );

  console.log("Response:", response.output?.text);
  console.log();
  console.log("Citations:");
  for (const citation of response.citations ?? []) {
    for (const ref of citation.retrievedReferences ?? []) {
      console.log(" -", ref.content?.text?.slice(0, 200));
    }
  }
} else {
  console.error(`Unknown mode '${MODE}'. Use 'retrieve' or 'generate'.`);
  process.exit(1);
}
