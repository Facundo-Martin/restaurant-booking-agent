import { table } from "./storage";
import { knowledgeBase } from "./ai";

const api = new sst.aws.ApiGatewayV2("RestaurantApi", {
  // TODO: Restrict to the Vercel domain once it's known (e.g. https://my-app.vercel.app)
  cors: {
    allowOrigins: ["*"],
    allowMethods: ["GET", "POST", "DELETE"],
    allowHeaders: ["*"],
  },
});

// Handles multi-turn agent conversations — sized for multiple Bedrock round trips
api.route("POST /chat", {
  handler: "backend/app/handler_chat.handler",
  runtime: "python3.11",
  architecture: "arm64",
  timeout: "120 seconds",
  memory: "1024 MB",
  link: [table, knowledgeBase],
  permissions: [
    {
      actions: ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      resources: [
        // Foundation model ARN (direct invocation)
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-7-sonnet-*",
        // Cross-region inference profile ARN (us.anthropic.* prefix routes through this)
        "arn:aws:bedrock:*:*:inference-profile/us.anthropic.claude-3-7-sonnet-*",
      ],
    },
  ],
});

// Simple DynamoDB reads/deletes — minimal resources, no Bedrock access needed
api.route("GET /bookings/{id}", {
  handler: "backend/app/handler_bookings.handler",
  runtime: "python3.11",
  architecture: "arm64",
  timeout: "10 seconds",
  memory: "256 MB",
  link: [table],
});

api.route("DELETE /bookings/{id}", {
  handler: "backend/app/handler_bookings.handler",
  runtime: "python3.11",
  architecture: "arm64",
  timeout: "10 seconds",
  memory: "256 MB",
  link: [table],
});

// Lightweight liveness check — useful for smoke testing after deploy
api.route("GET /health", {
  handler: "backend/app/handler_bookings.handler",
  runtime: "python3.11",
  architecture: "arm64",
  timeout: "10 seconds",
  memory: "256 MB",
});

// TODO: Attach WAF (aws.wafv2.WebAcl) with AWSManagedRulesCommonRuleSet and a per-IP rate-based rule
// TODO: Add authorizer to all routes once the user model is defined

export const url = api.url;
