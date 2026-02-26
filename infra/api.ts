import { table } from "./storage";
import { knowledgeBase } from "./ai";

const api = new sst.aws.ApiGatewayV2("RestaurantApi", {
  // TODO: Restrict to the frontend domain once it's known
  cors: {
    allowOrigins: ["*"],
    allowMethods: ["GET", "POST", "DELETE"],
    allowHeaders: ["*"],
  },
});

// Lambda Web Adapter layer — enables FastAPI/uvicorn to run in Lambda with response streaming.
// arm64 layer for the arm64 architecture used by all functions in this stack.
// https://github.com/awslabs/aws-lambda-web-adapter
const lwaLayerArn = "arn:aws:lambda:us-east-1:753240598075:layer:LambdaAdapterLayerArm64:26";

// Chat Lambda — uses LWA so FastAPI's StreamingResponse works natively.
// Bypasses API Gateway (which doesn't support streaming on HTTP APIs) via a Function URL.
// LWA starts uvicorn via run.sh, forwards the Lambda event as an HTTP request, and streams back.
export const chatFunction = new sst.aws.Function("ChatFunction", {
  handler: "backend/app/handler_chat.handler",
  runtime: "python3.11",
  architecture: "arm64",
  timeout: "120 seconds",
  memory: "1024 MB",
  link: [table, knowledgeBase],
  layers: [lwaLayerArn],
  environment: {
    // LWA invoke mode — must match the Function URL's InvokeMode
    AWS_LWA_INVOKE_MODE: "response_stream",
    // Port uvicorn listens on (LWA forwards to this)
    AWS_LWA_PORT: "8080",
    // Causes the Lambda runtime to exec the LWA bootstrap before the handler
    AWS_LAMBDA_EXEC_WRAPPER: "/opt/bootstrap",
    // LWA readiness check — poll /health until uvicorn is up
    AWS_LWA_READINESS_CHECK_PATH: "/health",
  },
  streaming: true,
  url: {
    cors: {
      allowOrigins: ["*"],
      allowMethods: ["POST"],
      allowHeaders: ["Content-Type"],
    },
  },
  permissions: [
    {
      actions: ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      resources: [
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-7-sonnet-*",
        "arn:aws:bedrock:*:*:inference-profile/us.anthropic.claude-3-7-sonnet-*",
      ],
    },
  ],
});

// Bookings and health routes — simple DynamoDB reads/writes, no streaming needed
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

// Lightweight liveness check
api.route("GET /health", {
  handler: "backend/app/handler_bookings.handler",
  runtime: "python3.11",
  architecture: "arm64",
  timeout: "10 seconds",
  memory: "256 MB",
});

// TODO: Attach WAF once the frontend domain is known
// TODO: Add authorizer once the user model is defined

export const url = api.url;
export const chatUrl = chatFunction.url;
