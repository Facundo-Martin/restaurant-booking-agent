# Restaurant Assistant — Technology & Migration Analysis

The goal of the project is to migrate https://github.com/strands-agents/samples/tree/main/02-samples/01-restaurant-assistant to a production-ready environment

## 1. Technology Map

### Application Layer

| Component           | Current Implementation                                                                                         |
| ------------------- | -------------------------------------------------------------------------------------------------------------- |
| **Agent Framework** | Strands Agents SDK (`strands-agents`)                                                                          |
| **LLM**             | Anthropic Claude 3.7 Sonnet via Amazon Bedrock (`us.anthropic.claude-3-7-sonnet-20250219-v1:0`)                |
| **Embedding Model** | Amazon Titan Embed Text v2 (`amazon.titan-embed-text-v2:0`)                                                    |
| **Built-in Tools**  | `current_time`, `retrieve` (from `strands-agents-tools`)                                                       |
| **Custom Tools**    | `get_booking_details` (inline `@tool`), `delete_booking` (module `@tool`), `create_booking` (`TOOL_SPEC` dict) |
| **Runtime**         | Jupyter Notebook                                                                                               |

### AWS Infrastructure

| Service                           | Role                          | Config                                                   |
| --------------------------------- | ----------------------------- | -------------------------------------------------------- |
| **Amazon Bedrock**                | LLM inference + KB retrieval  | Claude 3.7 Sonnet, thinking disabled                     |
| **Amazon Bedrock Knowledge Base** | RAG over restaurant/menu docs | FIXED_SIZE chunking, 512 tokens, 20% overlap             |
| **Amazon OpenSearch Serverless**  | Vector store backing the KB   | HNSW/faiss, 1024-dim, `AllowFromPublic: True`            |
| **Amazon S3**                     | Source documents for KB       | 12 `.docx` files (menus + directory)                     |
| **Amazon DynamoDB**               | Reservations store            | PAY_PER_REQUEST, PK: `booking_id`, SK: `restaurant_name` |
| **AWS SSM Parameter Store**       | Runtime config discovery      | KB ID + table name stored as parameters                  |
| **AWS IAM**                       | Service permissions           | Custom execution role for Bedrock KB → OSS + S3          |

### Infrastructure Provisioning

| Script                      | What it does                                                                                |
| --------------------------- | ------------------------------------------------------------------------------------------- |
| `deploy_prereqs.sh`         | Runs `knowledge_base.py` and `dynamodb.py` in create mode                                   |
| `prereqs/knowledge_base.py` | Imperatively creates S3, IAM roles, OSS collection+policies, KB, data source, ingestion job |
| `prereqs/dynamodb.py`       | Creates DynamoDB table, writes table name to SSM                                            |
| `cleanup.sh`                | Tears everything down in reverse                                                            |

### Infrastructure as Code (IaC) Map

#### Resource Catalog

**AI / ML**

- Amazon Bedrock (LLM runtime)
  - Foundation model policy — `bedrock:InvokeModel` on embedding + inference model ARNs (`knowledge_base.py:342`)
  - KB execution role trust policy — service principal `bedrock.amazonaws.com` (`knowledge_base.py:376`)
- Amazon Bedrock Knowledge Base
  - Execution role — `AmazonBedrockExecutionRoleForKnowledgeBase_{suffix}` (`knowledge_base.py:170`)
    - FM invocation policy — `bedrock:InvokeModel` scoped to embedding model ARN (`knowledge_base.py:173, 342`)
    - S3 read policy — `s3:GetObject`, `s3:ListBucket` on data bucket, account-scoped condition (`knowledge_base.py:176, 357`)
    - OSS API access policy — `aoss:APIAccessAll` on collection ARN (`knowledge_base.py:177, 454`)
  - Data source — S3-backed, FIXED_SIZE chunking, 512 tokens, 20% overlap (`knowledge_base.py:742`)
- Amazon OpenSearch Serverless (vector store)
  - Collection — VECTORSEARCH type (`knowledge_base.py:614`)
  - Vector index — HNSW/faiss, 1024-dim, L2 distance, 1 shard, 0 replicas (`knowledge_base.py:663`)
  - Encryption policy — AWS-owned key, scoped to collection (`knowledge_base.py:508`)
  - Network policy — `AllowFromPublic: True` ⚠️ security gap (`knowledge_base.py:530, 541`)
  - Data access policy — collection + index CRUD, principals: caller identity + KB execution role (`knowledge_base.py:554`)

**Storage**

- Amazon S3
  - Data bucket for KB source `.docx` documents (`knowledge_base.py:258`)
  - No resource-based policy; access controlled entirely via the KB execution role S3 policy (`knowledge_base.py:357`)
- Amazon DynamoDB
  - Table `restaurant-assistant-bookings` — PAY_PER_REQUEST billing (`dynamodb.py:48, 58`)
  - Composite key: PK `booking_id` (String, HASH), SK `restaurant_name` (String, RANGE) (`dynamodb.py:50`)
  - No table-level resource policy; access via caller's ambient IAM credentials

**Configuration**

- AWS SSM Parameter Store
  - `restaurant-assistant-kb-id` — written post-ingestion, read at agent startup (`knowledge_base.py:1066`)
  - `restaurant-assistant-table-name` — written post-table creation, read at agent startup (`dynamodb.py:65`)

---

#### SST v3 — Infrastructure Snippets

> **Important:** SST v3 is Pulumi-based, not CDK-based. There is no CDK escape hatch. Resources without a first-class SST component (Bedrock KB, OSS) are defined using raw Pulumi `aws.*` resources directly alongside SST components in `sst.config.ts`.

**Storage — SST first-class components**

```typescript
// sst.config.ts
// SST handles encryption, PITR, and least-privilege IAM automatically
const table = new sst.aws.Dynamo("Bookings", {
  fields: { booking_id: "string", restaurant_name: "string" },
  primaryIndex: { hashKey: "booking_id", rangeKey: "restaurant_name" },
});

// No public access by default
const kbBucket = new sst.aws.Bucket("KbDocuments");
```

**IAM — KB Execution Role (raw Pulumi `aws.*`)**

All three policies (FM, S3, OSS) are consolidated as `inlinePolicies` on the role — more idiomatic than separate `aws.iam.RolePolicy` resources when all policies belong to one role. `assumeRolePolicy` takes a plain JSON object directly; there is no `assumeRolePolicyForPrincipal` helper in Pulumi.

```typescript
// Raw Pulumi — no SST wrapper exists for IAM roles
// Mirrors knowledge_base.py:376 trust policy + three inline policies (lines 342, 357, 454)
const kbExecutionRole = new aws.iam.Role("KbExecutionRole", {
  // Direct JSON object — no helper function needed (knowledge_base.py:376)
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
      // FM policy (knowledge_base.py:342) — invoke embedding model
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
      // S3 policy (knowledge_base.py:357) — read source documents, account-scoped
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
      // OSS policy (knowledge_base.py:454) — API access to collection
      name: "KbOssPolicy",
      policy: ossCollection.arn.apply((collectionArn) =>
        JSON.stringify({
          Version: "2012-10-17",
          Statement: [
            {
              Effect: "Allow",
              Action: ["aoss:APIAccessAll"],
              Resource: collectionArn,
            },
          ],
        }),
      ),
    },
  ],
});
```

**OpenSearch Serverless — raw Pulumi `aws.*`**

> **Namespace correction:** OSS resources live under `aws.opensearch.Serverless*` in the Pulumi `aws` provider — not `aws.opensearchserverless.*` (which does not exist in the classic provider) and not `aws-native` (which lacks data access policy support per [pulumi-aws-native#2199](https://github.com/pulumi/pulumi-aws-native/issues/2199)). Use `aws` throughout.

Note that an encryption policy MUST exist before the collection can be created (knowledge_base.py:508). Reference https://www.pulumi.com/registry/packages/aws/api-docs/opensearch/serverlesscollection/

```typescript
// Encryption policy MUST exist before the collection can be created (knowledge_base.py:508) https://www.pulumi.com/registry/packages/aws/api-docs/opensearch/serverlesscollection/
// Pulumi provisions in parallel by default — dependsOn enforces the required ordering.
const ossEncryptionPolicy = new aws.opensearch.ServerlessSecurityPolicy(
  "OssEncryption",
  {
    name: "restaurant-assistant-enc",
    type: "encryption",
    policy: JSON.stringify({
      Rules: [
        {
          Resource: ["collection/restaurant-assistant"],
          ResourceType: "collection",
        },
      ],
      AWSOwnedKey: true,
    }),
  },
);

// Collection (knowledge_base.py:614)
const ossCollection = new aws.opensearch.ServerlessCollection(
  "VectorCollection",
  {
    name: "restaurant-assistant",
    type: "VECTORSEARCH",
  },
  { dependsOn: [ossEncryptionPolicy] },
); // encryption policy must exist first

// VPC — SST first-class component; provides the VPC ID and private subnets needed below.
// This is also what the API function (Phase 2) will be deployed into.
const vpc = new sst.aws.Vpc("RestaurantVpc", { nat: "managed" });

// OSS VPC Endpoint — required so the collection is reachable from within the VPC
// without AllowFromPublic. This is an OSS-specific endpoint, separate from a standard
// Interface VPC Endpoint. Its ID is what the network policy accepts as SourceVPCEs.
const ossVpcEndpoint = new aws.opensearch.ServerlessVpcEndpoint(
  "OssVpcEndpoint",
  {
    name: "restaurant-assistant-vpce",
    vpcId: vpc.id,
    subnetIds: vpc.privateSubnets,
    // securityGroupIds can be added here to restrict which resources inside the VPC can reach OSS
  },
);

// Network policy — VPC-scoped, replaces AllowFromPublic (knowledge_base.py:530, 541)
new aws.opensearch.ServerlessSecurityPolicy("OssNetwork", {
  name: "restaurant-assistant-net",
  type: "network",
  policy: ossVpcEndpoint.id.apply((vpceId) =>
    JSON.stringify([
      {
        Rules: [
          {
            Resource: ["collection/restaurant-assistant"],
            ResourceType: "collection",
          },
        ],
        AllowFromPublic: false,
        SourceVPCEs: [vpceId], // the OSS VPC endpoint defined above
      },
    ]),
  ),
});

// Data access policy (knowledge_base.py:554)
// aws.opensearch.ServerlessAccessPolicy — correct namespace; aws-native does not support this
new aws.opensearch.ServerlessAccessPolicy("OssDataAccess", {
  name: "restaurant-assistant-data",
  type: "data",
  policy: kbExecutionRole.arn.apply((roleArn) =>
    JSON.stringify([
      {
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
              "aoss:CreateIndex",
              "aoss:DeleteIndex",
              "aoss:UpdateIndex",
              "aoss:DescribeIndex",
              "aoss:ReadDocument",
              "aoss:WriteDocument",
            ],
          },
        ],
        Principal: [roleArn],
      },
    ]),
  ),
});
```

**Bedrock Knowledge Base + Data Source — raw Pulumi `aws.*` + `sst.Linkable.wrap()`**

> `pulumi.interpolate` and `.apply()` are functionally equivalent for string interpolation. `.apply()` is used here for consistency with Sean's pattern and because it composes more naturally when you need the value in a larger expression.
> The `AgentDataSource` is required — a KB without one retrieves nothing. It wires the S3 bucket and chunking strategy (knowledge_base.py:742) to the KB.

```typescript
// Knowledge Base (knowledge_base.py:771)
const knowledgeBase = new aws.bedrock.AgentKnowledgeBase(
  "RestaurantKB",
  {
    name: "restaurant-assistant",
    roleArn: kbExecutionRole.arn,
    knowledgeBaseConfiguration: {
      type: "VECTOR",
      vectorKnowledgeBaseConfiguration: {
        // .apply() used for consistency; pulumi.interpolate`` is equivalent for simple strings
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
        vectorIndexName: "restaurant-assistant-index",
        fieldMapping: {
          vectorField: "vector",
          textField: "text",
          metadataField: "text-metadata",
        },
      },
    },
  },
  { dependsOn: [kbExecutionRole] },
);

// S3 Data Source (knowledge_base.py:742, 751) — connects the KB to the S3 bucket with chunking config
// Without this, the KB has no documents and retrieve() returns nothing.
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
      fixedSizeChunkingConfiguration: {
        maxTokens: 512,
        overlapPercentage: 20,
      },
    },
  },
});
```

**Making the Knowledge Base Linkable to SST Functions**

By default, raw Pulumi resources are invisible to SST's `link` system. `sst.Linkable.wrap()` registers the Knowledge Base so that any SST function it is linked to will automatically receive its `id`, `arn`, and `name` as injectable properties, and will have `bedrock:Retrieve` + `bedrock:RetrieveAndGenerate` added to its execution role — no manual IAM policy needed.

```typescript
sst.Linkable.wrap(aws.bedrock.AgentKnowledgeBase, (kb) => ({
  properties: { id: kb.id, arn: kb.arn, name: kb.name },
  include: [
    sst.aws.permission({
      actions: ["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"],
      resources: [kb.arn],
    }),
  ],
}));
```

**API Function — linking everything together**

```typescript
// SST injects resource values at deploy time and grants IAM permissions automatically.
// No SSM Parameter Store needed at runtime.
const api = new sst.aws.Function("RestaurantApi", {
  handler: "backend/app/handler.handler",
  runtime: "python3.11",
  link: [table, kbBucket, knowledgeBase],
  url: true, // swap for sst.aws.ApiGatewayV2 when auth middleware is needed
});
```

---

#### SST v3 — Application Integration

This section shows how SST's `link` mechanism replaces SSM Parameter Store and connects the provisioned infrastructure to the Strands agent running inside a Lambda function.

**How `link` works**

SST does three things when you add a resource to `link: [...]`:

1. **Injects** the resource's properties (table name, KB ID, etc.) into the function at deploy time — encrypted in the function package, decrypted synchronously on cold start
2. **Grants IAM permissions** — the function's execution role automatically receives the policies defined by each linked resource (or by `sst.Linkable.wrap()`)
3. **Exposes** the values at runtime via `from sst import Resource`

No SSM calls, no hardcoded ARNs, no environment variable wrangling.

**`app/config.py` — replaces the SSM reads in the notebook**

```python
# Notebook (knowledge_base.py, dynamodb.py): two SSM network calls on every startup
# Production: zero network calls — values were injected at deploy time

from sst import Resource

TABLE_NAME = Resource.Bookings.name       # "restaurant-assistant-bookings-prod"
KB_ID      = Resource.RestaurantKB.id     # "ABCDEF1234"
```

**`app/tools/bookings.py` — shared client, no SSM**

```python
# Notebook: each tool re-initializes boto3 + makes an SSM call on every invocation
# Production: module-level client initialized once per Lambda cold start

import boto3
from strands import tool
from strands.types.tools import ToolResult, ToolUse
from app.config import TABLE_NAME
import uuid

_table = boto3.resource("dynamodb").Table(TABLE_NAME)

@tool
def get_booking_details(booking_id: str, restaurant_name: str) -> dict:
    """Get the relevant details for booking_id in restaurant_name."""
    response = _table.get_item(Key={"booking_id": booking_id, "restaurant_name": restaurant_name})
    return response.get("Item", f"No booking found with ID {booking_id}")

def create_booking(tool: ToolUse, **kwargs) -> ToolResult:
    # TOOL_SPEC stays the same; only the boto3 init changes
    item = {**tool["input"], "booking_id": str(uuid.uuid4())[:8]}
    _table.put_item(Item=item)
    return {"toolUseId": tool["toolUseId"], "status": "success",
            "content": [{"text": f"Reservation created: {item['booking_id']}"}]}

@tool
def delete_booking(booking_id: str, restaurant_name: str) -> str:
    """Delete an existing booking_id at restaurant_name."""
    _table.delete_item(Key={"booking_id": booking_id, "restaurant_name": restaurant_name})
    return f"Booking {booking_id} deleted successfully"
```

**`app/agent.py` — agent factory**

```python
import os
from strands import Agent
from strands.models import BedrockModel
from strands_tools import current_time, retrieve
from app.config import KB_ID
from app.tools.bookings import get_booking_details, create_booking, delete_booking

# retrieve tool reads KNOWLEDGE_BASE_ID from env — set once at module load
os.environ["KNOWLEDGE_BASE_ID"] = KB_ID

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

**Full architecture — how the layers interact**

```
sst.config.ts  (infra + wiring)
│
├── sst.aws.Dynamo("Bookings")                ─────────────────────────────┐
├── sst.aws.Bucket("KbDocuments")             ──────────────────────────┐  │
├── aws.opensearch.Serverless* (raw Pulumi)    ──► OSS collection        │  │
├── aws.bedrock.AgentKnowledgeBase            ──► KB                    │  │
│     └── sst.Linkable.wrap()  ◄── makes KB linkable                   │  │
│                                                                        │  │
└── sst.aws.Function("RestaurantApi")                                   │  │
      link: [Bookings, KbDocuments, RestaurantKB]                       │  │
      │   SST injects at deploy time:                                   │  │
      │     Resource.Bookings.name    ◄──────────────────────────────────  │
      │     Resource.KbDocuments.name ◄──────────────────────────────────────
      │     Resource.RestaurantKB.id  ◄── KB ID (was SSM)
      │   SST grants IAM:
      │     dynamodb:GetItem/PutItem/DeleteItem on Bookings table
      │     s3:GetObject/ListBucket on KbDocuments bucket
      │     bedrock:Retrieve/RetrieveAndGenerate on KB ARN
      │
      └── backend/app/handler.py  (Lambda entry point)
            └── backend/app/agent.py
                  from app.config import TABLE_NAME, KB_ID
                  │  (reads Resource.Bookings.name, Resource.RestaurantKB.id)
                  │
                  └── Strands Agent
                        tools: [retrieve, current_time,
                                get_booking_details, create_booking, delete_booking]
                               └── all use module-level _table = boto3...Table(TABLE_NAME)
```

**Project File Structure**

```
restaurant-assistant/
│
├── sst.config.ts                   # SST entry point — imports and wires all infra modules
├── package.json                    # SST + Node tooling deps
├── pnpm-workspace.yaml             # declares apps/* and infra as JS workspaces
├── turbo.json                      # Turborepo task pipeline (build, typecheck, lint)
├── tsconfig.json
│
├── infra/                          # SST infrastructure split into logical modules
│   ├── networking.ts               # sst.aws.Vpc + aws.opensearch.ServerlessVpcEndpoint
│   ├── storage.ts                  # sst.aws.Dynamo + sst.aws.Bucket
│   ├── ai.ts                       # IAM role, OSS collection+policies, KB, data source,
│   │                               #   sst.Linkable.wrap() — all AI/ML resources
│   ├── api.ts                      # sst.aws.Function (backend), link: [...], vpc: vpc
│   └── web.ts                      # sst.aws.Nextjs, link: [...], environment: {...}
│
├── apps/                           # Turborepo convention: deployable applications
│   └── web/                        # Next.js / React frontend
│       ├── package.json
│       ├── next.config.ts
│       ├── app/                    # Next.js App Router
│       │   ├── layout.tsx
│       │   ├── page.tsx            # Landing / chat page
│       │   └── globals.css
│       ├── components/
│       │   └── chat/
│       │       ├── ChatWindow.tsx  # Holds message history, manages SSE stream
│       │       ├── MessageBubble.tsx
│       │       └── ChatInput.tsx   # Input bar + send button
│       └── lib/
│           └── api.ts              # Generated typed fetch client → backend /chat endpoint
│
├── backend/                        # Python — FastAPI + Strands (outside pnpm workspaces)
│   ├── pyproject.toml              # uv workspace config (required for SST Python functions)
│   ├── app/
│   │   ├── handler.py              # Lambda entry point — wraps FastAPI with Mangum
│   │   ├── main.py                 # FastAPI app factory, mounts routers
│   │   ├── config.py               # from sst import Resource — single source of truth
│   │   ├── agent.py                # Strands Agent factory (create_agent())
│   │   │
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── chat.py         # POST /chat — streams agent response (SSE)
│   │   │       └── bookings.py     # GET/DELETE /bookings/:id — direct reservation mgmt
│   │   │
│   │   ├── tools/
│   │   │   └── bookings.py         # @tool: get_booking_details, create_booking,
│   │   │                           #   delete_booking — shared module-level boto3 client
│   │   └── models/
│   │       └── schemas.py          # Pydantic request/response models (ChatRequest, etc.)
│   │
│   └── tests/
│       ├── unit/
│       │   ├── tools/
│       │   │   └── test_bookings.py    # moto-mocked DynamoDB tool tests
│       │   └── agent/
│       │       └── test_agent.py       # agent factory + prompt regression tests
│       └── integration/
│           └── test_api.py             # FastAPI TestClient against live-ish endpoints
│
└── kb-documents/                   # Source .docx files uploaded to S3 on deploy
    ├── Restaurant Directory.docx
    ├── Rice and spice.docx
    └── ...                         # one file per restaurant menu
```

Key structural decisions:

- **`apps/web/`** follows the Turborepo convention of `apps/` for deployable applications and `packages/` for shared libraries. `backend/` stays at the root rather than inside `apps/` because Python is managed by `uv`, not pnpm — mixing them would be misleading
- **`infra/` modules** are imported and composed in `sst.config.ts` — keeps the root config clean and each concern independently readable
- **`backend/pyproject.toml`** at the package root is required by SST's `uv`-based Python bundler; all Python deps declared there
- **`handler.py`** uses [Mangum](https://github.com/jordaneremieff/mangum) to wrap FastAPI for Lambda — the same FastAPI app can also be run locally with `uvicorn app.main:app`
- **`apps/web/lib/api.ts`** is a generated typed client (via `@hey-api/openapi-ts` from FastAPI's OpenAPI spec) — not hand-written
- **`kb-documents/`** replaces `prereqs/kb_files/` — SST's deploy hook uploads these to the S3 bucket and triggers a KB sync ingestion job

---

### Monorepo Setup

#### Is this a monorepo?

Yes — a **polyglot monorepo**: one repository containing the SST infrastructure (TypeScript), the Next.js frontend (TypeScript), and the FastAPI + Strands backend (Python), all deployed as a unit. The "polyglot" part matters: standard JS workspace tooling only manages the TypeScript side. Python has its own workspace system entirely. The two are stapled together at the root.

#### Bootstrapping: SST template or manual?

**Start with the SST template, then adapt it.**

```bash
npm create sst@latest
```

This gives you the pieces that are tedious to configure manually:

- The correct `sst.config.ts` with the `async run() { await import("./infra/...") }` dynamic import pattern
- SST bootstrap scripts in `package.json`
- `.gitignore` entries for `.sst/` build artifacts

What to discard from the template: their `packages/functions`, `packages/core`, `packages/scripts` layout. That convention targets pure TypeScript Lambda monorepos. For this project, replace it with the `frontend/` and `backend/` layout above.

#### Workspace Tooling

| Layer              | Tool                | Manages                                           |
| ------------------ | ------------------- | ------------------------------------------------- |
| JS/TS packages     | **pnpm workspaces** | `frontend/`, `infra/`                             |
| Task orchestration | **Turborepo**       | build, typecheck, lint pipelines with caching     |
| Python             | **uv workspaces**   | `backend/` — required by SST for Python functions |
| Deploy + wiring    | **SST**             | ties both sides together per stage                |

**pnpm over npm:** strict dependency isolation (no phantom imports from hoisted `node_modules`), faster installs, and the de facto standard for JS monorepos in 2025.

**Turborepo over Nx:** Turborepo does one thing — fast task execution with caching. `turbo run build` knows which packages changed and skips the rest. Nx is a full platform with generators and module boundaries; valuable at 20+ packages, overkill here.

**Note:** pnpm workspaces only covers the JS side. `backend/` is excluded from `pnpm-workspace.yaml` and managed entirely by `uv`.

#### Frontend Directory Naming

Three conventions exist in the wild — they reflect tooling lineage more than personal preference:

| Name        | Convention                                                                    | Used by                                   |
| ----------- | ----------------------------------------------------------------------------- | ----------------------------------------- |
| `apps/web/` | Turborepo standard — `apps/` for deployable apps, `packages/` for shared libs | Vercel templates, most Turborepo starters |
| `www/`      | Older SST community shorthand; also seen in some open-source projects         | Some SST v2 projects, legacy repos        |
| `frontend/` | Descriptive, framework-agnostic                                               | Common in smaller or non-Turborepo setups |

We use **`apps/web/`** — it's the Turborepo idiom and scales correctly if a second app is added (e.g. `apps/admin/`). The SST infra file that provisions it is named `infra/web.ts` to match.

#### Root Config Files

**`pnpm-workspace.yaml`**

```yaml
packages:
  - "apps/*" # picks up apps/web and any future apps (apps/admin, etc.)
  - "infra"
  # backend intentionally omitted — Python is managed by uv, not pnpm
```

**`turbo.json`**

```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": [".next/**", "!.next/cache/**"]
    },
    "typecheck": { "dependsOn": ["^build"] },
    "lint": {},
    "dev": { "cache": false, "persistent": true }
  }
}
```

**Root `package.json`**

```json
{
  "name": "restaurant-assistant",
  "private": true,
  "scripts": {
    "dev": "sst dev",
    "deploy": "sst deploy",
    "build": "turbo run build",
    "typecheck": "turbo run typecheck",
    "lint": "turbo run lint"
  },
  "devDependencies": {
    "sst": "latest",
    "aws": "npm:@pulumi/aws",
    "turbo": "latest"
  }
}
```

**`sst.config.ts`**

```typescript
export default $config({
  app(input) {
    return {
      name: "restaurant-assistant",
      removal: input?.stage === "production" ? "retain" : "remove",
      protect: ["production"].includes(input?.stage),
      home: "aws",
    };
  },
  async run() {
    const networking = await import("./infra/networking");
    const storage = await import("./infra/storage");
    const ai = await import("./infra/ai");
    const api = await import("./infra/api");
    await import("./infra/frontend");

    return {
      ApiUrl: api.url,
      KbId: ai.knowledgeBaseId,
    };
  },
});
```

**`backend/pyproject.toml`** (uv workspace — required by SST Python bundler)

```toml
[tool.uv.workspace]
members = ["app"]

[project]
name = "restaurant-assistant-backend"
requires-python = ">=3.11"
dependencies = [
  "fastapi",
  "mangum",
  "strands-agents",
  "strands-agents-tools",
  "boto3",
  "sst",
]

[tool.uv.sources]
sst = { git = "https://github.com/sst/sst.git", subdirectory = "sdk/python", branch = "dev" }
```

#### TS ↔ Python Contract

The frontend (TypeScript) and backend (Python) share no runtime code — the only contract between them is the HTTP API shape. Keep it type-safe by generating a TypeScript client from FastAPI's auto-generated OpenAPI spec:

```
FastAPI ──► openapi.json ──► @hey-api/openapi-ts ──► apps/web/lib/api.ts
```

Add a root script to regenerate on schema changes:

```json
"generate:client": "cd backend && uvicorn app.main:app & sleep 2 && curl localhost:8000/openapi.json > ../apps/web/openapi.json && cd ../apps/web && npx @hey-api/openapi-ts"
```

This means `frontend/lib/api.ts` is always a generated, typed client — no manual fetch wrappers, no string-typed endpoint URLs.

#### What do other teams use?

| Team / Project            | JS tooling       | Python | Notes                                         |
| ------------------------- | ---------------- | ------ | --------------------------------------------- |
| Vercel (Next.js, v0)      | pnpm + Turborepo | —      | Turborepo is their own product                |
| Linear                    | pnpm workspaces  | —      | Custom task scripts, no Turborepo             |
| Planetscale               | pnpm + Turborepo | —      |                                               |
| Most mid-size SaaS (2025) | pnpm + Turborepo | uv     | Industry default                              |
| SST template              | npm workspaces   | —      | No Turborepo; fine for small TS-only projects |
| Vinta (Next.js + FastAPI) | pnpm             | uv     | OpenAPI schema as the TS↔Python contract      |

---

## 2. Current State — POC Gaps

These are the specific issues that block production use.

### Code Structure

- `create_booking.py` and `delete_booking.py` are generated at runtime via Jupyter `%%writefile` magic — not proper Python modules
- Each tool re-initializes its own `boto3` client + SSM call on every invocation (no connection reuse)
- No input sanitization beyond what the LLM prompt enforces

### Infrastructure

- OSS network policy has `"AllowFromPublic": True` — exposes the vector index to the internet
- Infrastructure managed by ad-hoc Python scripts (no IaC — no drift detection, no state tracking)
- No VPC; all services accessed over public endpoints

### Operability

- Agent state (conversation history in `agent.messages`) lives purely in notebook memory — no persistence
- No structured logging, no distributed tracing, no alerting
- No API surface — only invocable from the notebook REPL
- No authentication or authorization on any layer

### Reliability

- No retry/circuit-breaker logic at the tool layer (beyond what the Bedrock SDK provides)
- No test suite (unit, integration, or load)

---

## 3. High-Level Migration Plan

### Phase 0 — Project Restructuring (prerequisite for everything else)

Convert the notebook into a proper Python package:

```
restaurant-assistant/
├── app/
│   ├── agent.py           # Agent factory
│   ├── tools/
│   │   ├── bookings.py    # All 3 DynamoDB tools, shared boto3 client
│   │   └── retrieval.py   # KB tool config
│   ├── config.py          # Env-based config (replaces SSM ad-hoc reads)
│   └── api/               # Phase 2
├── infra/                 # Phase 1
├── tests/                 # Phase 1
└── requirements.txt
```

### Phase 1 — Infrastructure as Code + Security Hardening

- Replace `knowledge_base.py` / `dynamodb.py` scripts with **SST v3** (Pulumi-based IaC)
- Deploy all services into a **VPC** with private subnets + VPC endpoints for Bedrock, DynamoDB, S3
- Remove `AllowFromPublic` from OSS — replace with VPC-based access policy
- Enforce least-privilege IAM: separate roles for the agent runtime vs. the KB ingestion pipeline
- Manage secrets/config through **AWS Secrets Manager** (sensitive) and **SSM Parameter Store** (non-sensitive)

### Phase 2 — API Layer + Session Management

- Wrap the agent in a **FastAPI** application (or deploy as **AWS Lambda + API Gateway** for serverless)
- Add **Amazon Cognito** (or API key validation) for authentication at the API layer
- Persist conversation history to **DynamoDB** (session table) so conversations survive process restarts and scale horizontally
- Add request/response validation with Pydantic models

### Phase 3 — Observability

- Emit structured JSON logs via Python `logging` with correlation IDs threaded through all tool calls
- Add **AWS X-Ray** tracing on all Bedrock and DynamoDB calls
- Publish custom **CloudWatch metrics**: latency per tool, token usage per request, booking success/failure rate
- Set up **CloudWatch Alarms** on error rates and p99 latency

### Phase 4 — Testing + CI/CD

- Unit tests for each tool (mock boto3 with `moto`)
- Integration tests against a localstack or sandbox environment
- Prompt regression tests: a fixed set of user inputs with expected tool call sequences (catches model behavior drift)
- **GitHub Actions** (or AWS CodePipeline) for: lint → test → `sst diff` → deploy to staging → smoke test → promote to prod

### Phase 5 — Deployment Target

Two viable paths depending on traffic profile:

| Path                      | Best for                               | Trade-offs                                                           |
| ------------------------- | -------------------------------------- | -------------------------------------------------------------------- |
| **Lambda + API GW**       | Bursty / low baseline traffic          | Cold starts (~1–2s), 15-min max execution, simple ops                |
| **ECS Fargate (FastAPI)** | Sustained traffic, streaming responses | Always-on cost, more control over concurrency and connection pooling |

> The streaming nature of Strands agents (token-by-token output) favors **ECS + ALB** with Server-Sent Events or WebSockets over Lambda's synchronous response model.

---

## 4. Summary

The current sample is a well-structured educational demo that clearly illustrates Strands' tool definition patterns and Bedrock integrations. The migration path is straightforward because the core logic is sound — the gaps are almost entirely **operational** (no IaC, no API layer, no persistence, no observability, public network exposure). None of the agent logic needs to be redesigned.

**Recommended starting point:** Phase 0 (project restructuring), since it unblocks all subsequent phases.
