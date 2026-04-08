# EDD Hardening: Eval Framework Pivot — Braintrust → Strands Evals

**Date:** 2026-04-07
**Status:** Plan updated — ready to implement Strands Evals approach
**Previous:** `2026-04-04-edd-hardening-discovery-poc.md` (autoevals + Braintrust gateway)

---

## Background: The Braintrust Gateway Journey

### Initial Goal
Centralize all eval scoring in **Braintrust** using the **Braintrust Gateway** to route LLM calls to multiple providers (OpenAI, Bedrock, Anthropic) through a unified API. This would enable:
- Easy provider switching without code changes
- Unified observability and experiment tracking in Braintrust UI
- Automatic caching and rate-limit management via the gateway

### What Went Wrong (In Order)

#### 1. **OpenAI API Key Issues (13:20–13:40)**
- Initial setup: configured Braintrust gateway with OpenAI provider
- `autoevals` library was reading `OPENAI_API_KEY` from environment directly, bypassing the gateway
- Old/stale API key in `.env` caused `401 Unauthorized` errors: `"Incorrect API key provided: sk-proj-..."`
- **Lesson:** autoevals has hardcoded OpenAI dependency for embeddings; it doesn't respect the gateway client

#### 2. **Removed OpenAI Key, Code/UI Out of Sync (13:40–14:00)**
- Deleted `OPENAI_API_KEY` from `.env`
- Switched to Bedrock provider in Braintrust UI
- Added only **embeddings models** to Braintrust config:
  - `amazon.titan-embed-text-v2:0`
  - `cohere.embed-english-v3`
- **Problem:** These are embeddings-only models; autoevals needs a chat/completions model for the scoring logic
- Error: `400 Bad Request - Unexpected field type` (embeddings endpoint can't handle chat completions requests)
- **Lesson:** Braintrust UI and code must stay perfectly in sync; generic error messages don't help

#### 3. **Model Name Format Mismatch (14:00–14:20)**
- Tried using Bedrock ARN format: `us.meta.llama3-1-8b-instruct-v1:0`
- Braintrust gateway returned: `404 Not Found - unknown model`
- Other models worked with simpler format: `cohere.embed-english-v3`, `amazon.titan-embed-text-v2:0`
- **Lesson:** Braintrust has its own model naming conventions; AWS ARN format doesn't translate directly

#### 4. **Inference Profile Requirement Discovery (14:20–14:40)**
- Tested Bedrock access directly: `aws bedrock-runtime invoke-model --model-id meta.llama3-1-8b-instruct-v1:0`
- **Error:** `ValidationException: Invocation of model ID meta.llama3-1-8b-instruct-v1:0 with on-demand throughput isn't supported. Retry your request with the ID or ARN of an inference profile.`
- AWS Bedrock requires **inference profiles** for on-demand access; can't call models directly
- **Lesson:** AWS documentation for this was sparse; error message didn't clearly explain the solution

#### 5. **Inference Profile Setup (14:40–15:00)**
- Created inference profile via AWS CLI: `aws bedrock create-inference-profile --inference-profile-name llama-eval-profile ...`
- Got the profile ARN: `arn:aws:bedrock:us-east-1:288813394681:inference-profile/us.meta.llama3-1-8b-instruct-v1:0`
- Tested it directly: ✅ worked with `aws bedrock-runtime invoke-model`
- Added to Braintrust UI as a model
- **Lesson:** Had to debug AWS internals directly; Braintrust's generic errors provided no guidance

#### 6. **Final Blocker: autoevals Doesn't Use Gateway (15:00–15:20)**
- After all of the above, reran eval with correct inference profile ID
- **Still failing** with `400 Bad Request - Unexpected field type`
- Root cause: **`autoevals` library internally uses embeddings for scoring**, and these calls are **hardcoded to use OpenAI directly**
- The `init(openai.AsyncOpenAI(...))` call configures the scoring logic to route through the gateway, but autoevals' internal embedding step reads `OPENAI_API_KEY` from the environment
- **No amount of Braintrust gateway configuration fixes this.** autoevals was never designed to work with arbitrary models through a gateway
- **Lesson:** Documentation doesn't state this limitation. Autoevals is coupled to OpenAI by design.

#### 7. **OpenAI Quota Hit (15:20–15:40)**
- Created a new valid OpenAI API key and added it to Braintrust
- Configured it as the provider in Braintrust UI
- Ran eval again
- **Error:** OpenAI account exceeded quota (over limit, would require payment)
- **Decision:** Not paying for eval scoring when Bedrock is already provisioned

---

## Why This Happened: Root Causes

1. **autoevals Library Limitation:** Designed for OpenAI-compatible APIs, with hardcoded embedding dependencies. Gateway routing doesn't help because autoevals bypasses the configured client for its internal steps.

2. **Documentation Gaps:**
   - Braintrust docs don't warn that autoevals won't work with arbitrary models routed through the gateway
   - autoevals docs don't list which providers it actually supports
   - AWS Bedrock's inference profile requirement is buried in error messages
   - Generic HTTP errors from the gateway provide no context

3. **Multi-System Coordination:** Integrating three systems (Braintrust gateway, AWS Bedrock, autoevals) required them all to agree on model names, formats, and capabilities. One misconfiguration cascaded into failures across all three.

---

## The Pivot: Strands Evals

After research, discovered that **Strands Evals** is the official, documented approach recommended by the Strands team for evaluating agents built with Strands Agents SDK.

### Why Strands Evals is Better for This Use Case

1. **Native to Strands Agents:** No gateway nonsense, works directly with Bedrock
2. **Comprehensive Evaluators Built-in:**
   - `HelpfulnessEvaluator` (like agent_helpfulness_scorer)
   - `FaithfulnessEvaluator` (grounding in context — replaces autoevals)
   - `ToolSelectionAccuracyEvaluator` (like tool_routing)
   - `ToolParameterAccuracyEvaluator`
   - `GoalSuccessRateEvaluator`
   - `ActorSimulator` for multi-turn conversations

3. **No Gateway Complexity:** Calls Bedrock directly, avoids routing/translation layer
4. **Well-Documented:** Official AWS/Strands blog posts with concrete examples
5. **Designed for Agents:** All concepts (Cases, Experiments, Evaluators, multi-turn simulation) map to agent eval workflows

### Trade-off: Fragmented Observability
- Eval data lives in Strands logs, not Braintrust
- **Mitigation:** Use Braintrust for offline production trace analysis later (separate concern)

---

## New Architecture: Hybrid Approach

### Development / CI
**Tool:** Strands Evals
**When:** During development, before code review, in CI pipeline
**What:** Comprehensive evaluation with:
- RAG quality (faithfulness, relevance)
- Agent behavior (helpfulness, tool accuracy)
- Multi-turn conversations (ActorSimulator)
- Fast feedback loop for regressions

**Output:** Strands telemetry + CLI reports

### Production Monitoring
**Tool:** Braintrust (offline evaluation)
**When:** Post-deployment, periodic analysis of real traffic
**What:** Offline evaluation of production traces:
- Custom scorers for production patterns
- Long-term trending and alerting
- Stakeholder-facing dashboards

**Output:** Braintrust experiment history + metadata

---

## Implementation Plan

### Phase 1: Replace Braintrust Eval with Strands Evals (This Session)
1. Create `backend/evals/strands/eval_discovery.py`
2. Define discovery test cases (reuse from `backend/evals/cases/discovery.py`)
3. Use Strands built-in evaluators
4. Run end-to-end and verify
5. Document how to run locally and in CI

### Phase 2: Archive Braintrust (Next Session)
1. Keep `backend/evals/braintrust/` for future offline production eval setup
2. Remove autoevals + gateway routing code (it's dead weight now)
3. Update CI pipeline to run Strands Evals instead of Braintrust

### Phase 3: Offline Production Eval (Future)
1. When prod agent is live, set up Braintrust to ingest production traces
2. Configure offline evaluators on real user interactions
3. Track long-term trends and regressions

---

## Lessons Learned

1. **Use the tool designed for the job.** Strands Evals exists specifically for Strands Agents; Braintrust is more general-purpose.
2. **Integration debt is real.** Routing through a gateway adds a translation layer that can silently fail (autoevals still uses OpenAI).
3. **Read official guidance first.** The Strands blog posts should have been the starting point, not autoevals + Braintrust gateway.
4. **Error messages matter.** Generic `400 Bad Request` errors from the gateway wasted hours. Direct AWS CLI errors were more informative.
5. **One place for observability is sometimes a myth.** It's OK to use Strands Evals for dev and Braintrust for prod—they serve different purposes.

---

## Next Steps

- [ ] Implement Strands Evals eval runner
- [ ] Verify it runs discovery eval successfully
- [ ] Add to CI/CD pipeline
- [ ] Document how to run locally for development
- [ ] Archive Braintrust gateway code
