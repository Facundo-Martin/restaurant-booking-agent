# Architecture Analysis — Restaurant Booking Agent

Reference: SST v3 Infrastructure Snippets in `project.MD`.
This document tracks design findings, antipatterns, security issues, and constraints for the **target** architecture only.

---

## Target Architecture Overview

```
Internet
  │
  └── API Gateway HTTP API (sst.aws.ApiGatewayV2 "RestaurantApi")
        │
        ├── POST /chat
        │     └── sst.aws.Function "RestaurantChat"  [Python 3.11, Mangum + FastAPI, 120s, 1024MB]
        │           │  link: [Bookings, KbDocuments, RestaurantKB]
        │           │  permissions: [bedrock:InvokeModel]
        │           │
        │           └── Strands Agent
        │                 ├── BedrockModel (Claude 3.7 Sonnet)
        │                 ├── retrieve      ──► Bedrock KB ──► OSS (via VPCE)
        │                 ├── current_time
        │                 ├── get_booking_details ──► DynamoDB
        │                 ├── create_booking      ──► DynamoDB
        │                 └── delete_booking      ──► DynamoDB
        │
        └── GET /bookings/{id}, DELETE /bookings/{id}
              └── sst.aws.Function "RestaurantBookings"  [Python 3.11, 10s, 256MB]
                    │  link: [Bookings]
                    └── DynamoDB

RestaurantVpc (sst.aws.Vpc)  ← no NAT; Lambda is NOT VPC-attached
  └── private subnets         VPC exists solely to host the OSS VPC endpoint
        └── OssVpcEndpoint (aws.opensearch.ServerlessVpcEndpoint)
              └── OSS Collection "restaurant-assistant" (VECTORSEARCH)
                    └── vector index (HNSW/faiss, 1024-dim)

Bedrock Knowledge Base "RestaurantKB"
  └── S3 data source (KbDocuments bucket, FIXED_SIZE 512t/20% overlap)
  └── storage: OSS collection (via kbExecutionRole)

sst.aws.Dynamo "Bookings"
  └── PK: booking_id (String), SK: restaurant_name (String)

sst.aws.Bucket "KbDocuments"
  └── .docx source files for KB ingestion
```

---

## Security Issues

### Critical

**~~Lambda Function URL has no authentication (`url: true`)~~** ✅ Resolved
`url: true` replaced with `sst.aws.ApiGatewayV2`. Auth middleware (Cognito authorizer or Lambda authorizer) to be added in a later phase once the user model is defined.

**Lambda missing `bedrock:InvokeModel` permission**
`sst.Linkable.wrap()` grants only `bedrock:Retrieve` and `bedrock:RetrieveAndGenerate` on the KB ARN. The Lambda also needs `bedrock:InvokeModel` on the Claude 3.7 Sonnet model ARN for the Strands agent's LLM calls. This permission is absent from all infra snippets — the function will fail at runtime on the first agent invocation.
- Fix: Add an explicit `sst.aws.permission` for `bedrock:InvokeModel` scoped to the exact model ARN in `infra/api.ts`.

**OSS VPC endpoint has no security group**
The `ossVpcEndpoint` definition leaves `securityGroupIds` commented out. Without a security group, the endpoint accepts connections from any ENI in the private subnets — including any future Lambda or ECS workload added to the VPC.
- Fix: Create a dedicated security group allowing HTTPS (443) only from the Lambda function's security group, and attach it to the endpoint.

### High

**`aoss:APIAccessAll` on the KB execution role IAM policy**
The inline `KbOssPolicy` grants `aoss:APIAccessAll` on the collection ARN. This is a wildcard action covering collection-level admin operations (not just data read/write). The separate OSS data access policy correctly uses fine-grained permissions (`aoss:ReadDocument`, `aoss:WriteDocument`, etc.) — the IAM policy should mirror the same scope.
- Fix: Replace `aoss:APIAccessAll` with the minimum set: `aoss:APIAccessAll` is the only action available at the IAM level for OSS (it's the single action that unlocks data-plane access). The data access policy is where fine-grained control lives. However, scoping the IAM resource to the specific collection ARN (which the snippet already does) is the correct approach here — this is actually acceptable as-is, but worth noting.

**Deployer identity not in the OSS data access policy**
The original POC included both the caller identity and the KB execution role as principals in the data access policy. The target data access policy only includes `kbExecutionRole.arn`. This means the person running `sst deploy` (or any CI role) cannot inspect or manage the OSS index directly (e.g., to verify ingestion, debug index content). Not strictly a security issue, but an operational gap.
- Fix: Add the deployer's IAM role or a dedicated ops role as a second principal in `OssDataAccess`.

**No WAF**
Without WAF there is no OWASP managed ruleset, no rate limiting per IP, and no bot detection.
- Fix: Now that API Gateway is in place, attach `aws.wafv2.WebAcl` (scope `REGIONAL`) to the API Gateway stage with `AWSManagedRulesCommonRuleSet` and a per-IP rate-based rule. Tracked in `infrastructure.md` section 6.

---

## Antipatterns

### Infrastructure

**Hard-coded resource names are not stage-aware**
The collection name `"restaurant-assistant"`, encryption/network/data-access policy names, and OSS index name are all literal strings. Deploying to a second stage (e.g., `staging`) in the same AWS account will either conflict with existing resources or result in policies that don't match the collection name.

Affected locations in `project.MD`:
- `ossEncryptionPolicy`: `"collection/restaurant-assistant"` (line ~190)
- `ossCollection`: `name: "restaurant-assistant"` (line ~204)
- `ossVpcEndpoint`: `name: "restaurant-assistant-vpce"` (line ~220)
- `OssNetwork` policy: `"collection/restaurant-assistant"` (line ~236)
- `OssDataAccess` policy: `"collection/restaurant-assistant"`, `"index/restaurant-assistant/*"` (lines ~259, ~267)
- KB name: `name: "restaurant-assistant"` (line ~296)
- Data source name: `"restaurant-assistant-s3"` (line ~330)

Fix: Derive names from the SST app name + stage, e.g.:
```typescript
const collectionName = `${$app.name}-${$app.stage}`;
```
Then reference this variable everywhere instead of the string literal.

**`$resolve(kbBucket.arn).apply((arn) => arn)` is a no-op**
In the `s3DataSource` definition (`project.MD` line ~334), the bucket ARN is wrapped in `$resolve(...).apply((arn) => arn)` — this resolves an SST Output to a Pulumi Output and immediately returns it unchanged. It adds indirection without effect.
- Fix: Use `$resolve(kbBucket.arn)` directly, or pass `kbBucket.arn` if SST has already resolved it to a Pulumi Output in that context.

**`dependsOn: [kbExecutionRole]` on the KB is incomplete**
The `knowledgeBase` resource declares `dependsOn: [kbExecutionRole]` but the KB also requires the OSS collection to exist and be active. The OSS collection depends on the encryption policy. If Pulumi resolves the KB before the collection is fully active, the KB creation will fail.
- Fix: `dependsOn: [kbExecutionRole, ossCollection]` — or better, rely on the `collectionArn` reference in the storage configuration to create an implicit dependency, which Pulumi tracks automatically. The explicit `dependsOn` on the role is still needed since the role ARN is referenced via `.apply()` in the `Linkable.wrap()` call, not in the resource body itself.

**KB ingestion is not triggered post-deploy**
The architecture uploads `.docx` files to `KbDocuments` on deploy, but no SST deploy hook or Pulumi custom resource is shown to trigger a Bedrock KB ingestion job afterward. Without ingestion, the KB has no embeddings and `retrieve()` returns nothing.
- Fix: Add an SST `transform` or a `aws.bedrock.AgentDataSourceStartIngestionJob` resource (or a custom Pulumi resource using the AWS SDK) that starts an ingestion job after the data source is created.

### Application

**`create_agent()` is a factory, not a singleton**
`agent.py` defines `create_agent()` but if `chat.py` calls this on every request, the `BedrockModel` object is re-instantiated on every warm invocation. The Strands agent object holds no per-request state that would require re-creation.
- Fix: Cache the agent at module level:
```python
_agent = create_agent()
```
Then use `_agent` in the route handler. Re-creation is only needed on cold start.

**`booking_id` uses `uuid4()[:8]` — truncated and collision-prone**
8 hex characters give ~4 billion possible values. With ~65k existing bookings, the birthday collision probability exceeds 1 in 1000. Booking IDs should be both collision-resistant and unpredictable.
- Fix: Use the full `str(uuid.uuid4())` or a KSUID (time-ordered, URL-safe).

**`delete_booking` returns success even if the booking does not exist**
DynamoDB `delete_item` is a no-op when the key is not found — no error is raised. The tool returns `"Booking deleted successfully"` regardless, which the agent will relay to the user as confirmation of a deletion that may never have happened.
- Fix: Use a `ConditionExpression` (`attribute_exists(booking_id)`) and catch `ConditionalCheckFailedException` to return an accurate result.

**No Lambda timeout or memory configured**
The `sst.aws.Function` snippet has no `timeout` or `memory` property. SST's default Lambda timeout is 10 seconds — far too short for a multi-tool Bedrock agent interaction (multiple LLM round trips + DynamoDB + OSS latency). Default memory is 1024MB in SST but should be explicit.
- Fix: Set `timeout: "120 seconds"` and confirm `memory: "1024 MB"` in `infra/api.ts`.

**Mangum buffers the entire response — SSE streaming will not work**
The `chat.py` route is designed to stream SSE tokens from the Strands agent. Mangum converts Lambda events to ASGI requests, but it buffers the complete response body before returning it to Lambda. FastAPI's `StreamingResponse` will appear to hang until the full agent response is ready, then deliver it all at once.
- Fix (pick one):
  1. Enable Lambda response streaming (`invoke_mode: "RESPONSE_STREAM"`) and replace Mangum with a raw ASGI streaming handler.
  2. Switch to ECS Fargate + ALB, which supports true HTTP streaming without buffering constraints.
  3. Accept buffered responses and drop the SSE design — return the complete agent response as a single JSON body.

---

## Infrastructure Constraints

**OpenSearch Serverless minimum cost**
OSS bills a baseline of 2 OCUs for indexing + 2 OCUs for search regardless of traffic — approximately **$345/month** at current pricing. This cost is incurred even with zero queries. For a staging environment or a low-traffic demo, OSS is the dominant cost line.
- Mitigation: Share a single OSS collection across stages (use separate indexes per stage). Or evaluate Aurora PostgreSQL with pgvector as an alternative vector store — no minimum OCU cost, scales to zero with Aurora Serverless v2.

**~~No VPC endpoints for Bedrock, DynamoDB, or S3~~** ✅ Not applicable
Lambda is NOT VPC-attached. It calls DynamoDB and Bedrock directly over AWS public endpoints using IAM — no NAT, no VPC routing. Bedrock's own service plane (using the KB execution role) reaches OSS through the OSS VPC endpoint. No additional VPC endpoints are needed.

**~~Lambda is not placed in the VPC~~** ✅ Resolved
Lambda is intentionally NOT VPC-attached. The VPC exists solely to host the `aws.opensearch.ServerlessVpcEndpoint`, which gives Bedrock's KB service plane private access to the OSS collection. `nat: "managed"` has been removed from the VPC — it served no purpose without VPC-resident compute.

**OSS VPC endpoint provisioning time**
OSS VPC endpoints take 10–30 minutes to provision on first deploy. The `sst deploy` will appear to hang during this step. This is an AWS limitation — no workaround, but worth setting expectations.

**OSS vector index: 0 replicas**
The index is configured with `"number_of_replicas": 0`. OSS manages the underlying nodes, but zero replicas means no redundancy at the index level. During maintenance or shard rebalancing, queries may fail.
- Fix: Set `"number_of_replicas": 1` for any persistent environment.

**No DynamoDB GSI for user or restaurant queries**
The table schema (PK: `booking_id`, SK: `restaurant_name`) supports direct key lookups only. Any query like "show all bookings for user X" or "all reservations at Restaurant Y" requires a full table scan.
- Fix: Add a GSI with `restaurant_name` as hash key (and optionally `date` as range key) in the `sst.aws.Dynamo` definition.

**Single Lambda for all routes**
`/chat` (Bedrock agent, needs long timeout + substantial memory) and `/bookings/:id` (simple DynamoDB CRUD, needs ~3s timeout + minimal memory) share the same Lambda function. Every bookings request pays for a function sized for an LLM workload.
- Fix: Split into two functions in `infra/api.ts`: `RestaurantChatApi` and `RestaurantBookingsApi`, with independent timeout and memory settings.

---

## Decision Log

| Decision | Current | Recommended | Status |
|---|---|---|---|
| API exposure | Lambda Function URL | API Gateway HTTP API + authorizer | **Decided: API Gateway HTTP API** |
| Frontend hosting | `sst.aws.Nextjs` | Vercel — better DX, preview URLs, free tier | **Decided: Vercel** |
| Streaming | SSE via Mangum | Lambda Response Streaming or ECS Fargate | Unresolved — deferred |
| Stage-aware naming | Hard-coded `"restaurant-assistant"` | Derived from `$app.name`+`$app.stage` | Not yet addressed |
| Vector store | OSS ~$345/month (always-on) | OSS with `removal: "remove"` — tear down when idle; Aurora Serverless v2 + pgvector if always-on needed | **Decided: keep OSS, tear down when idle** |
| Lambda in VPC | Unspecified | Lambda is NOT VPC-attached; VPC only hosts OSS endpoint; NAT removed | **Decided: Lambda outside VPC** |
| KB ingestion trigger | Not shown | Deploy hook or Pulumi custom resource | Not yet addressed |
