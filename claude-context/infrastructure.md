# Infrastructure — Restaurant Booking Agent

All AWS infrastructure organized by category. Each section contains the target SST/Pulumi snippet and a checklist of open issues for that resource.

---

## 1. Networking — `infra/networking.ts`

VPC exists solely to host the OSS VPC endpoint, which gives Bedrock's KB service plane private access to the OSS collection with `AllowFromPublic: false`. Lambda is **not** VPC-attached — it reaches DynamoDB and Bedrock directly via IAM over AWS public endpoints. No NAT gateway is needed.

```typescript
// VPC — no NAT; Lambda is not VPC-attached so no internet egress is needed from within the VPC
const vpc = new sst.aws.Vpc("RestaurantVpc", { nat: "none" });

// OSS-specific VPC endpoint — not a standard aws.ec2.VpcEndpoint.
// Bedrock's KB service plane uses this endpoint (via kbExecutionRole) to reach OSS privately.
// Its ID is referenced as SourceVPCEs in the OSS network policy.
const ossVpcEndpoint = new aws.opensearch.ServerlessVpcEndpoint("OssVpcEndpoint", {
  name: "restaurant-assistant-vpce",
  vpcId: vpc.id,
  subnetIds: vpc.privateSubnets,
  // securityGroupIds: [] — see todos
});

export { vpc, ossVpcEndpoint };
```

**Todos:**
- [x] `securityGroupIds` is empty on `ossVpcEndpoint` — create a dedicated security group allowing TCP 443 inbound only from within the VPC (or scoped to Bedrock's service-plane CIDR if deterministic), and attach it here

---

## 2. Storage — `infra/storage.ts`

```typescript
// SST handles encryption, PITR, and least-privilege IAM automatically
const table = new sst.aws.Dynamo("Bookings", {
  fields: { booking_id: "string", restaurant_name: "string" },
  primaryIndex: { hashKey: "booking_id", rangeKey: "restaurant_name" },
});

// No public access by default
const kbBucket = new sst.aws.Bucket("KbDocuments");

export { table, kbBucket };
```

**Todos:**
- [x] No GSI defined — the table only supports direct key lookups. Queries like "all bookings at Restaurant X" or "bookings on date Y" require a full table scan. Add a GSI with `restaurant_name` as hash key and `date` as range key:
  ```typescript
  globalIndexes: {
    ByRestaurantDate: {
      hashKey: "restaurant_name",
      rangeKey: "date",
      projection: "all",
    }
  }
  ```

---

## 3. IAM — `infra/ai.ts`

Execution role used by the Bedrock KB service plane to read from S3 and write to OSS.

```typescript
const kbExecutionRole = new aws.iam.Role("KbExecutionRole", {
  assumeRolePolicy: {
    Version: "2012-10-17",
    Statement: [{
      Effect: "Allow",
      Principal: { Service: "bedrock.amazonaws.com" },
      Action: "sts:AssumeRole",
      Condition: {
        StringEquals: { "aws:SourceAccount": aws.getCallerIdentityOutput().accountId },
      },
    }],
  },
  inlinePolicies: [
    {
      name: "KbFmPolicy",
      policy: aws.getRegionOutput().name.apply((region) =>
        JSON.stringify({
          Version: "2012-10-17",
          Statement: [{
            Effect: "Allow",
            Action: ["bedrock:InvokeModel"],
            Resource: `arn:aws:bedrock:${region}::foundation-model/amazon.titan-embed-text-v2:0`,
          }],
        }),
      ),
    },
    {
      name: "KbS3Policy",
      policy: $resolve(kbBucket.arn).apply((arn) =>
        JSON.stringify({
          Version: "2012-10-17",
          Statement: [{
            Effect: "Allow",
            Action: ["s3:GetObject", "s3:ListBucket"],
            Resource: [arn, `${arn}/*`],
          }],
        }),
      ),
    },
    {
      name: "KbOssPolicy",
      policy: ossCollection.arn.apply((collectionArn) =>
        JSON.stringify({
          Version: "2012-10-17",
          Statement: [{
            Effect: "Allow",
            Action: ["aoss:APIAccessAll"],
            Resource: collectionArn,
          }],
        }),
      ),
    },
  ],
});
```

**Todos:**
- [ ] No issues with this resource — `aoss:APIAccessAll` is the only IAM-level action available for OSS data-plane access; fine-grained control lives in the OSS data access policy. The resource is already scoped to the specific collection ARN

---

## 4. OpenSearch Serverless — `infra/ai.ts`

> **Namespace:** OSS resources use `aws.opensearch.Serverless*` from the classic `aws` provider. Do not use `aws.opensearchserverless.*` (does not exist in the classic provider) or `aws-native` (lacks data access policy support).

```typescript
// Encryption policy MUST be created before the collection
const ossEncryptionPolicy = new aws.opensearch.ServerlessSecurityPolicy("OssEncryption", {
  name: "restaurant-assistant-enc",
  type: "encryption",
  policy: JSON.stringify({
    Rules: [{ Resource: ["collection/restaurant-assistant"], ResourceType: "collection" }],
    AWSOwnedKey: true,
  }),
});

const ossCollection = new aws.opensearch.ServerlessCollection("VectorCollection", {
  name: "restaurant-assistant",
  type: "VECTORSEARCH",
}, { dependsOn: [ossEncryptionPolicy] });

// Network policy — VPC-only, AllowFromPublic: false
new aws.opensearch.ServerlessSecurityPolicy("OssNetwork", {
  name: "restaurant-assistant-net",
  type: "network",
  policy: ossVpcEndpoint.id.apply((vpceId) =>
    JSON.stringify([{
      Rules: [{ Resource: ["collection/restaurant-assistant"], ResourceType: "collection" }],
      AllowFromPublic: false,
      SourceVPCEs: [vpceId],
    }]),
  ),
});

// Data access policy — fine-grained index + collection permissions
new aws.opensearch.ServerlessAccessPolicy("OssDataAccess", {
  name: "restaurant-assistant-data",
  type: "data",
  policy: kbExecutionRole.arn.apply((roleArn) =>
    JSON.stringify([{
      Rules: [
        {
          ResourceType: "collection",
          Resource: ["collection/restaurant-assistant"],
          Permission: [
            "aoss:CreateCollectionItems",
            "aoss:DeleteCollectionItems",
            "aoss:UpdateCollectionItems",
            "aoss:DescribeCollectionItems",
          ],
        },
        {
          ResourceType: "index",
          Resource: ["index/restaurant-assistant/*"],
          Permission: [
            "aoss:CreateIndex", "aoss:DeleteIndex", "aoss:UpdateIndex",
            "aoss:DescribeIndex", "aoss:ReadDocument", "aoss:WriteDocument",
          ],
        },
      ],
      Principal: [roleArn],
    }]),
  ),
});
```

**Todos:**
- [ ] All resource names are hard-coded string literals (`"restaurant-assistant"`, `"restaurant-assistant-enc"`, etc.) — deploying a second stage in the same account will conflict. Derive names from the SST stage:
  ```typescript
  const collectionName = `${$app.name}-${$app.stage}`;
  ```
  Then use `collectionName` everywhere instead of the literal string
- [ ] `OssDataAccess` only lists `kbExecutionRole.arn` as a principal — no operator or CI role can inspect index contents or debug ingestion. Add the deployer's IAM role (or a dedicated ops role) as a second principal with at minimum `aoss:DescribeIndex` and `aoss:ReadDocument`
- [ ] The vector index is configured with `"number_of_replicas": 0` — no redundancy. Set to `1` for any non-ephemeral environment
- [ ] OSS bills a baseline of 2 OCUs (indexing) + 2 OCUs (search) regardless of traffic — approximately **$345/month** at zero queries. For dev/staging: share one collection across stages using separate index names per stage, relying on `removal: "remove"` to tear it down between sessions. Alternative: Aurora Serverless v2 + pgvector (~$46/month minimum, scales to zero) — Bedrock KB supports both with no agent code changes

---

## 5. Bedrock Knowledge Base — `infra/ai.ts`

```typescript
const knowledgeBase = new aws.bedrock.AgentKnowledgeBase("RestaurantKB", {
  name: "restaurant-assistant",
  roleArn: kbExecutionRole.arn,
  knowledgeBaseConfiguration: {
    type: "VECTOR",
    vectorKnowledgeBaseConfiguration: {
      embeddingModelArn: aws.getRegionOutput().name.apply(
        (region) => `arn:aws:bedrock:${region}::foundation-model/amazon.titan-embed-text-v2:0`,
      ),
    },
  },
  storageConfiguration: {
    type: "OPENSEARCH_SERVERLESS",
    opensearchServerlessConfiguration: {
      collectionArn: ossCollection.arn,
      vectorIndexName: "restaurant-assistant-index",
      fieldMapping: { vectorField: "vector", textField: "text", metadataField: "text-metadata" },
    },
  },
}, { dependsOn: [kbExecutionRole] });

const s3DataSource = new aws.bedrock.AgentDataSource("RestaurantKBDataSource", {
  knowledgeBaseId: knowledgeBase.id,
  name: "restaurant-assistant-s3",
  dataSourceConfiguration: {
    type: "S3",
    s3Configuration: {
      bucketArn: $resolve(kbBucket.arn).apply((arn) => arn),
    },
  },
  vectorIngestionConfiguration: {
    chunkingConfiguration: {
      chunkingStrategy: "FIXED_SIZE",
      fixedSizeChunkingConfiguration: { maxTokens: 512, overlapPercentage: 20 },
    },
  },
});

// Registers the raw Pulumi resource with SST's link system
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
```

**Todos:**
- [ ] `dependsOn: [kbExecutionRole]` is incomplete — KB creation also requires the OSS collection to be in `ACTIVE` state. Change to `dependsOn: [kbExecutionRole, ossCollection]`
- [ ] KB ingestion is never triggered after deploy — uploading `.docx` files to S3 does not automatically sync the KB. Without an ingestion run the KB has zero embeddings and `retrieve()` returns nothing. Add a post-deploy trigger: an `aws.bedrock.AgentDataSourceIngestionJob` resource (or a Pulumi dynamic resource calling the SDK) that starts a sync job after `s3DataSource` is created
- [ ] `$resolve(kbBucket.arn).apply((arn) => arn)` in `s3DataSource` is a no-op — it resolves an SST Output to a Pulumi Output and returns it unchanged. Replace with `$resolve(kbBucket.arn)` directly

---

## 6. API / Lambda — `infra/api.ts`

API Gateway HTTP API with two separate Lambda functions — one sized for the Bedrock agent workload, one for simple DynamoDB CRUD.

```typescript
const api = new sst.aws.ApiGatewayV2("RestaurantApi");

// POST /chat — long timeout and full memory for multi-tool Bedrock agent interactions
api.route("POST /chat", {
  handler: "backend/app/handler_chat.handler",
  runtime: "python3.11",
  timeout: "120 seconds",
  memory: "1024 MB",
  link: [table, kbBucket, knowledgeBase],
  permissions: [{
    actions: ["bedrock:InvokeModel"],
    resources: ["arn:aws:bedrock:*::foundation-model/anthropic.claude-3-7-sonnet-*"],
  }],
});

// Bookings CRUD — minimal resources, DynamoDB only
api.route("GET /bookings/{id}", {
  handler: "backend/app/handler_bookings.handler",
  runtime: "python3.11",
  timeout: "10 seconds",
  memory: "256 MB",
  link: [table],
});

api.route("DELETE /bookings/{id}", {
  handler: "backend/app/handler_bookings.handler",
  runtime: "python3.11",
  timeout: "10 seconds",
  memory: "256 MB",
  link: [table],
});

export const url = api.url;
```

**Todos:**
- [ ] No WAF — attach `aws.wafv2.WebAcl` (scope `REGIONAL`) to the API Gateway stage with `AWSManagedRulesCommonRuleSet` and a per-IP rate-based rule
- [ ] No auth on any route — add a Cognito User Pool authorizer or Lambda authorizer to `POST /chat` once the user model is defined. Bookings routes should be similarly protected
- [ ] **Mangum buffers the full response** — `StreamingResponse` from `/chat` will not stream; Mangum collects the entire body before returning it to Lambda. Deferred decision — pick one when implementing the backend:
  1. Enable `invoke_mode: "RESPONSE_STREAM"` and replace Mangum with a raw ASGI streaming adapter
  2. Drop SSE and return the complete agent response as a single JSON body (simplest path)

---

## 7. Application — `backend/`

The backend Python code is not yet written. These are issues present in the `project.MD` snippets that will carry forward into the implementation.

**`backend/app/agent.py`**

```python
def create_agent() -> Agent:
    model = BedrockModel(
        model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        additional_request_fields={"thinking": {"type": "disabled"}},
    )
    return Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[retrieve, current_time, get_booking_details, create_booking, delete_booking],
    )
```

**Todos:**
- [ ] `create_agent()` is called as a factory — if `chat.py` calls it per request, a new `BedrockModel` is instantiated on every warm invocation. Cache at module level:
  ```python
  _agent = create_agent()  # executed once per cold start
  ```

---

**`backend/app/tools/bookings.py`**

```python
def create_booking(tool: ToolUse, **kwargs) -> ToolResult:
    item = {**tool["input"], "booking_id": str(uuid.uuid4())[:8]}
    _table.put_item(Item=item)
    ...

@tool
def delete_booking(booking_id: str, restaurant_name: str) -> str:
    _table.delete_item(Key={"booking_id": booking_id, "restaurant_name": restaurant_name})
    return f"Booking {booking_id} deleted successfully"
```

**Todos:**
- [ ] `uuid.uuid4()[:8]` produces only 8 hex characters (~4 billion values) — collision probability exceeds 0.1% at ~65k bookings. Use the full `str(uuid.uuid4())`
- [ ] `delete_booking` returns `"Booking deleted successfully"` unconditionally — `delete_item` is a no-op when the key is not found and raises no error. The agent will confirm a deletion that never happened. Add a `ConditionExpression`:
  ```python
  _table.delete_item(
      Key={"booking_id": booking_id, "restaurant_name": restaurant_name},
      ConditionExpression="attribute_exists(booking_id)",
  )
  # catch ConditionalCheckFailedException and return a not-found result
  ```
