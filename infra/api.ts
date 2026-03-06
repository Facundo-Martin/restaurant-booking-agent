import { table, sessionsBucket } from "./storage";
import { knowledgeBase, guardrail } from "./ai";

// Langfuse OTLP auth header — set via: sst secret set LangfuseAuthHeader "Authorization=Basic <base64(pk:sk)>"
// If not set, the OTEL_EXPORTER_OTLP_ENDPOINT env var is omitted and Strands telemetry is skipped.
const langfuseAuthHeader = new sst.Secret("LangfuseAuthHeader");

// Lambda Powertools env vars — shared across all functions.
// POWERTOOLS_LOG_LEVEL is stage-aware: WARNING in production reduces log volume
// and CloudWatch cost; INFO elsewhere gives full visibility during development.
const powertoolsEnv = {
  POWERTOOLS_SERVICE_NAME: "restaurant-booking",
  POWERTOOLS_METRICS_NAMESPACE: "RestaurantBookingAgent",
  POWERTOOLS_LOG_LEVEL: $app.stage === "production" ? "WARNING" : "INFO",
  // Exposed to Python config.py for trace_attributes stage tagging in Langfuse
  APP_STAGE: $app.stage,
};

export const api = new sst.aws.ApiGatewayV2("RestaurantApi", {
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
  link: [table, knowledgeBase, sessionsBucket, guardrail],
  layers: [lwaLayerArn],
  environment: {
    ...powertoolsEnv,
    // LWA invoke mode — must match the Function URL's InvokeMode
    AWS_LWA_INVOKE_MODE: "response_stream",
    // Port uvicorn listens on (LWA forwards to this)
    AWS_LWA_PORT: "8080",
    // Causes the Lambda runtime to exec the LWA bootstrap before the handler
    AWS_LAMBDA_EXEC_WRAPPER: "/opt/bootstrap",
    // LWA readiness check — poll /health until uvicorn is up
    AWS_LWA_READINESS_CHECK_PATH: "/health",
    // Prevent raw user messages (which may contain PII) from appearing verbatim
    // in OTEL trace span attributes — caps any single attribute value at 512 chars
    OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT: "512",
    // Langfuse OTLP trace export — only active when LangfuseAuthHeader secret is set.
    // main.py guards on OTEL_EXPORTER_OTLP_ENDPOINT being present before calling setup_otlp_exporter().
    OTEL_EXPORTER_OTLP_ENDPOINT: "https://us.cloud.langfuse.com/api/public/otel",
    OTEL_EXPORTER_OTLP_HEADERS: langfuseAuthHeader.value,
    OTEL_TRACES_SAMPLER: "traceidratio",
    OTEL_TRACES_SAMPLER_ARG: $app.stage === "production" ? "0.1" : "1.0",
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

// Shared config for all bookings-Lambda routes — simple DynamoDB reads/writes,
// no streaming needed.
const bookingsRouteConfig = {
  handler: "backend/app/handler_bookings.handler",
  runtime: "python3.11" as const,
  architecture: "arm64" as const,
  timeout: "10 seconds" as const,
  memory: "256 MB" as const,
  environment: powertoolsEnv,
};

api.route("GET /bookings/{id}", { ...bookingsRouteConfig, link: [table] });
api.route("DELETE /bookings/{id}", { ...bookingsRouteConfig, link: [table] });

// Lightweight liveness check — no table link needed
api.route("GET /health", bookingsRouteConfig);

// TODO: Attach WAF once the frontend domain is known
// TODO: Add authorizer once the user model is defined

export const url = api.url;
export const chatUrl = chatFunction.url;
