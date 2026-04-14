# EDD Hardening: Evaluation-Driven Development Architecture

**Date:** 2026-04-04
**Status:** Design (awaiting approval)
**Scope:** Foundational evaluation architecture for the Restaurant Booking Agent
**POC Feature:** Discovery (single-turn restaurant search)
**Target Implementation Time:** 4 hours (with parallel development)

---

## 1. Overview & Goals

### Problem Statement

The Restaurant Booking Agent requires rigorous, reproducible evaluation at the **feature level**, not just end-to-end. Different features have different quality criteria:
- **Discovery:** RAG quality, faithfulness, proactivity
- **Reservations:** Confirmation handling, required field gathering, correct booking creation
- **Cancellations:** Booking ID verification, confirmation, graceful ID lookup failures
- **Updates:** Field identification, confirmation, validation
- **Support:** Proactive suggestions, graceful degradation, alternative offerings

Without clear, feature-scoped evaluation metrics defined upfront, we risk:
- Implementing features that appear to work but fail in production
- Difficulty comparing versions (is prompt V2 better than V1?)
- No regression detection when changes break existing behavior
- Tight coupling between implementation and testing (hard to refactor)

### Solution: Evaluation-Driven Development (EDD)

**EDD means:**
1. **Define features clearly** — as user stories with acceptance criteria
2. **Define scoring strategies upfront** — what "good" means for each feature
3. **Build test datasets that cover the full surface** — happy path, edge cases, failure modes
4. **Implement scorers systematically** — autoevals for broad signals, custom code for deterministic checks, LLM-as-judge for nuance
5. **Integrate evaluation into CI/CD** — catch regressions before production

### This Spec Covers

- **Feature definitions** for Discovery (POC) and outlines for other features
- **Evaluation architecture** — file structure, scorer organization, test case design
- **Scoring strategies** — which scorers, why, thresholds, shared vs. feature-specific
- **Implementation roadmap** — step-by-step, with file paths and deliverables
- **Scalability plan** — how this architecture grows to 5 features without duplication

---

## 2. Feature Definitions & Acceptance Criteria

### Feature: Discovery (POC)

**What it is:**
Single-turn user queries about restaurants. The agent retrieves relevant restaurants from the knowledge base and synthesizes a helpful response.

**User story:**
> As a user, I want to search for restaurants by cuisine, location, or preferences so that I can discover dining options that match my needs.

**Core requirements (non-negotiable):**

1. **Correctness** — Agent returns factually accurate restaurants matching the query
2. **Faithfulness** — Agent doesn't hallucinate restaurants or details not in the KB
3. **Helpfulness** — Agent offers alternatives or clarifications when appropriate
4. **Trust** — No PII leakage, no misleading information

**Acceptance Criteria:**
- ✓ Agent correctly calls `retrieve` tool with appropriate search terms
- ✓ Retrieved context is relevant to the user's question
- ✓ Final response uses only facts from retrieved context (no hallucinations)
- ✓ Response is clear, well-formatted, and helpful
- ✓ Response suggests alternatives if results are limited (proactivity)
- ✓ Response doesn't leak other users' reservation data
- ✓ ContextRelevancy score ≥ 0.7
- ✓ Faithfulness score ≥ 0.8 (critical)
- ✓ AnswerRelevancy score ≥ 0.7
- ✓ Agent Helpfulness score ≥ 0.7
- ✓ Tool Routing = 1.0 (must call retrieve)
- ✓ Data Privacy = 1.0 (no PII)

### Features: Reservations, Cancellations, Updates (Defined Later)

**Reservations:**
- Agent gathers required fields (restaurant, date, time, party size)
- Agent asks for clarification if ambiguous
- Agent confirms booking details before creating
- Agent creates correct booking (no hallucinations)

**Cancellations:**
- Agent verifies booking ID (exact or lookup)
- Agent asks for confirmation before cancelling
- Agent handles "not found" gracefully (suggests alternatives)
- Agent cancels correct booking

**Updates:**
- Agent identifies which field to update
- Agent gathers new value with clarification if needed
- Agent confirms change before updating
- Agent applies correct update with validation

**Support (Overall):**
- Agent proactively suggests alternatives when primary path fails
- Agent offers guidance without being pushy
- Agent gracefully handles edge cases and ambiguity
- Agent maintains user trust even in failure scenarios

---

## 3. Evaluation Architecture

### 3.1 File Structure

```
backend/evals/
├── __init__.py
├── cases/                          # Test case definitions (by feature)
│   ├── __init__.py
│   ├── discovery.py               # 15-18 test cases for discovery feature
│   ├── reservations.py            # 12-15 test cases for reservations (future)
│   ├── cancellations.py           # 12-15 test cases for cancellations (future)
│   ├── updates.py                 # 12-15 test cases for updates (future)
│   ├── support.py                 # 10-12 test cases for support (future)
│   └── common.py                  # Shared utilities (EvalCase, constants)
│
├── braintrust/                     # Braintrust eval runners (by feature)
│   ├── __init__.py
│   ├── config.py                  # Shared constants (project, dataset names)
│   ├── manifest.py                # EvalMetadata (commit, model IDs, scorer version)
│   ├── datasets.py                # Dataset loading helpers with preflight guards
│   ├── discovery.py               # Eval runner for discovery POC
│   ├── reservations.py            # Eval runner for reservations (future)
│   ├── cancellations.py           # Eval runner for cancellations (future)
│   ├── updates.py                 # Eval runner for updates (future)
│   └── support.py                 # Eval runner for support (future)
│
├── scorers/                        # Scorer implementations (framework-agnostic)
│   ├── __init__.py
│   ├── common/                    # Shared across features
│   │   ├── __init__.py
│   │   ├── booking_operations.py  # user_confirmation_required, correct_tool_called, no_action_without_consent
│   │   ├── data_privacy.py        # data_privacy (applies to ALL 5 features)
│   │   └── tool_routing.py        # tool_routing_correctness (extensible to all features)
│   │
│   ├── discovery/                 # Discovery-specific scorers
│   │   ├── __init__.py
│   │   ├── rag_quality.py         # Composite: ContextRelevancy + Faithfulness + AnswerRelevancy
│   │   ├── agent_helpfulness.py   # LLM-as-judge: is the response helpful?
│   │   ├── agent_proactivity.py   # LLM-as-judge: does it offer alternatives?
│   │   ├── prompts/               # Prompt templates for LLM-as-judge scorers
│   │   │   ├── helpfulness.txt
│   │   │   └── proactivity.txt
│   │   └── README.md              # Discovery scorer documentation
│   │
│   ├── reservations/              # Reservations-specific scorers (future)
│   │   ├── __init__.py
│   │   └── README.md
│   │
│   ├── cancellations/             # Cancellations-specific scorers (future)
│   │   ├── __init__.py
│   │   └── README.md
│   │
│   ├── updates/                   # Updates-specific scorers (future)
│   │   ├── __init__.py
│   │   └── README.md
│   │
│   └── support/                   # Support-specific scorers (future)
│       ├── __init__.py
│       └── README.md
│
├── strands/                        # Strands-specific eval runners (unchanged)
│   ├── __init__.py
│   ├── test_agent_evals.py
│   ├── output_quality_eval.py
│   ├── trajectory_eval.py
│   └── otel_scaffold.py
│
└── EVALUATION_ARCHITECTURE.md      # This design document
```

### 3.2 Separation of Concerns

| Component | Purpose | Scope |
|---|---|---|
| **Cases** | Test data definitions | Feature-scoped |
| **Braintrust runners** | Eval orchestration | Framework-specific |
| **Scorers (common)** | Reusable evaluation logic | Cross-feature |
| **Scorers (feature-specific)** | Feature-unique evaluation logic | Feature-scoped |
| **Prompts** | LLM-as-judge scoring rubrics | Scorer-scoped |
| **Config** | Constants, identifiers | Global |

**Key principle:** A scorer can be reused across features if its evaluation criterion is universal (e.g., `data_privacy`, `user_confirmation_required`). Feature-specific scorers live in their feature's folder.

---

## 4. Test Case Design

### 4.1 Test Case Structure

Every test case is an `EvalCase` with:
```python
@dataclass(frozen=True)
class EvalCase:
    id: str                    # stable identifier (used in Braintrust)
    input: str                 # user message
    expected: dict             # evaluation rubric (not strict answer)
    metadata: dict             # categorization and debugging
```

**Example for Discovery:**
```python
EvalCase(
    id="discovery-filtered-italian-downtown",
    input="Show me Italian restaurants downtown",
    expected={
        "should_call": ["retrieve"],
        "description": "Call retrieve tool with query about Italian restaurants downtown. Return 2-5 restaurants with name, cuisine, hours, and location. Do NOT invent restaurants or details."
    },
    metadata={
        "query_type": "filtered_search",  # basic | filtered | ambiguous | edge_case
        "difficulty": "medium",            # easy | medium | hard
        "expected_tools": ["retrieve"],
        "category": "discovery",
        "tags": ["cuisine_filter", "location_filter"]
    }
)
```

### 4.2 Discovery Dataset Composition

**Total: 15-18 test cases**

| Category | Count | Purpose | Examples |
|---|---|---|---|
| **Basic Searches** | 5 | Validate core retrieval | "What restaurants do you have?", "Show me Italian places", "Restaurant options?" |
| **Filtered Searches** | 5 | Validate KB search precision | "Italian restaurants downtown", "Vegetarian options in midtown", "Upscale dining" |
| **Ambiguous Queries** | 3 | Validate agent judgment & clarification | "Something nice for a date", "Best place to eat", "Popular restaurants" |
| **Edge Cases** | 2-3 | Validate handling of tricky inputs | Typos ("Itilian"), vague preferences ("Good food"), contradictions ("cheap AND luxurious") |
| **Boundary Cases** | 1-2 | Validate graceful handling | Very broad queries ("Any food?"), hyper-specific queries ("sushi with gluten-free soy sauce") |

**Total: 16-18 cases** — manageable, representative, room to grow as you identify failure patterns.

---

## 5. Scoring Strategy

### 5.1 Scorers for Discovery

**Seven scorers total: 4 autoevals + 2 LLM-as-judge + 1 custom code**

#### Autoevals (from `autoevals` library)

| Scorer | What it measures | Why for Discovery | Pass Threshold | Cost |
|---|---|---|---|---|
| **ContextRelevancy** | Is retrieved KB context relevant to the query? | Validate retrieval quality | ≥ 0.7 | $ (LLM call) |
| **Faithfulness** | Does answer stick to retrieved context? | Prevent hallucinations | ≥ 0.8 (critical) | $ (LLM call) |
| **AnswerRelevancy** | Is answer relevant to the question? | Validate answer-question alignment | ≥ 0.7 | $ (LLM call) |

**Composite scorer:** These three are related (all RAG quality). We return them from a single scorer function to reduce overhead:

```python
def rag_quality_scorer(input, output, context, **kwargs):
    """Composite RAG quality scorer returning 3 scores."""
    return [
        ContextRelevancy()(input=input, output=output, context=context),
        Faithfulness()(input=input, output=output, context=context),
        AnswerRelevancy()(input=input, output=output),
    ]
```

#### LLM-as-Judge Scorers

| Scorer | What it measures | Why for Discovery | Pass Threshold | Cost |
|---|---|---|---|---|
| **Agent Helpfulness** | Is the response helpful, clear, well-formatted? | Validate UX quality | ≥ 0.7 | $ (LLM call) |
| **Agent Proactivity** | Does it offer alternatives or clarifications? | Validate "Overall Support" on Discovery | ≥ 0.6 (nice-to-have) | $ (LLM call) |

**Implemented as:** Natural language rubrics evaluated by Claude Haiku via Bedrock.

#### Custom Code Scorers

| Scorer | What it measures | Why for Discovery | Pass Threshold | Cost |
|---|---|---|---|---|
| **Tool Routing** | Did agent call `retrieve` tool? | Validate agent correctly uses KB | 1.0 (must-have) | None (deterministic) |
| **Data Privacy** | No PII/user data leakage? | Protect user trust | 1.0 (must-have) | None (regex patterns) |

### 5.2 Scoring Logic & Thresholds

**Three tiers of requirements:**

1. **Hard Stops (1.0 required):**
   - Tool Routing (must call retrieve)
   - Data Privacy (no PII leakage)
   - If either fails, the test fails regardless of other scores

2. **Critical (≥ 0.8 required):**
   - Faithfulness (hallucinations are unacceptable)
   - Core requirement for production

3. **Standard (≥ 0.7 required):**
   - ContextRelevancy, AnswerRelevancy, Helpfulness
   - Expected quality bar for production-ready responses

4. **Nice-to-Have (≥ 0.6 required):**
   - Proactivity (measure agent going above and beyond)
   - Not core but improves user experience

**Test result:** A test **passes** if ALL hard stops are 1.0, faithfulness ≥ 0.8, and standard scorers ≥ 0.7. Proactivity can dip to 0.6 without failing.

---

## 6. Scorer Implementations

### 6.1 Composite RAG Quality Scorer

**File:** `backend/evals/scorers/discovery/rag_quality.py`

```python
"""Composite RAG quality scorer returning 3 related scores.

This scorer bundles ContextRelevancy, Faithfulness, and AnswerRelevancy
into a single scorer function to reduce LLM call overhead while maintaining
clarity of individual scores.

Why composite: These three are tightly related (all measure RAG quality),
so combining them reduces redundant processing while keeping scores separate
for debugging.
"""

from autoevals import ContextRelevancy, Faithfulness, AnswerRelevancy
from braintrust import Score

async def rag_quality_scorer(
    input: str,
    output: str,
    **kwargs
) -> list[Score]:
    """
    Composite scorer: returns 3 separate RAG quality scores.

    Args:
        input: User query
        output: Agent response (final answer)
        kwargs: May include 'context' (retrieved documents) from task function

    Returns:
        List of 3 Score objects:
          - ContextRelevancy: relevance of retrieved context to query
          - Faithfulness: whether answer adheres to retrieved context
          - AnswerRelevancy: relevance of answer to question
    """
    context = kwargs.get("context", "")  # Retrieved docs passed by task function

    return [
        ContextRelevancy()(input=input, output=output, context=context),
        Faithfulness()(input=input, output=output, context=context),
        AnswerRelevancy()(input=input, output=output),
    ]
```

### 6.2 LLM-as-Judge Scorer: Agent Helpfulness

**File:** `backend/evals/scorers/discovery/agent_helpfulness.py`

```python
"""LLM-as-judge scorer: is the agent response helpful?"""

import boto3
from braintrust import Score

# Read prompt template from file
with open("backend/evals/scorers/discovery/prompts/helpfulness.txt") as f:
    HELPFULNESS_PROMPT_TEMPLATE = f.read()

async def agent_helpfulness_scorer(
    input: str,
    output: str,
    **kwargs
) -> Score:
    """
    LLM-as-judge scorer: evaluate helpfulness of the agent response.

    Uses Claude Haiku via Bedrock to rate the response on clarity,
    completeness, and user-friendliness.
    """
    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

    prompt = HELPFULNESS_PROMPT_TEMPLATE.format(input=input, output=output)

    response = bedrock.invoke_model(
        modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        body=json.dumps({
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
        })
    )

    result = json.loads(response["body"].read())
    score_text = result["content"][0]["text"].strip()

    # Parse score (0-1) from model output
    score = float(score_text.split('\n')[0])

    return Score(
        name="Agent Helpfulness",
        score=score,
        metadata={"reasoning": score_text}
    )
```

**Prompt file:** `backend/evals/scorers/discovery/prompts/helpfulness.txt`

```
You are evaluating a restaurant discovery response.

User Query: {{input}}
Agent Response: {{output}}

Rate the helpfulness of this response on a scale of 0-1:
- 1.0: Clear, well-formatted list with all relevant details (names, cuisine, hours, location). Professional tone.
- 0.7: Helpful but missing minor details or could be clearer.
- 0.4: Somewhat helpful but confusing, incomplete, or poorly formatted.
- 0.0: Unhelpful, truncated, incoherent, or doesn't address the query.

Consider:
- Is the restaurant list easy to read and understand?
- Are restaurant names clearly stated?
- Are key details (cuisine, hours, location) included?
- Is the tone friendly and professional?
- Is the response well-structured?

Return ONLY a single number between 0 and 1 on the first line.
Then explain your reasoning.
```

### 6.3 LLM-as-Judge Scorer: Agent Proactivity

**File:** `backend/evals/scorers/discovery/agent_proactivity.py`

```python
"""LLM-as-judge scorer: is the agent proactive and helpful?"""

import boto3
from braintrust import Score

# Read prompt template from file
with open("backend/evals/scorers/discovery/prompts/proactivity.txt") as f:
    PROACTIVITY_PROMPT_TEMPLATE = f.read()

async def agent_proactivity_scorer(
    input: str,
    output: str,
    **kwargs
) -> Score:
    """
    LLM-as-judge scorer: evaluate proactivity of the agent response.

    Does the agent go above and beyond to help the user?
    - Suggest alternatives if results are limited
    - Ask clarifying questions if query is ambiguous
    - Offer next steps (filtering, booking)
    """
    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

    prompt = PROACTIVITY_PROMPT_TEMPLATE.format(input=input, output=output)

    response = bedrock.invoke_model(
        modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        body=json.dumps({
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
        })
    )

    result = json.loads(response["body"].read())
    score_text = result["content"][0]["text"].strip()
    score = float(score_text.split('\n')[0])

    return Score(
        name="Agent Proactivity",
        score=score,
        metadata={"reasoning": score_text}
    )
```

**Prompt file:** `backend/evals/scorers/discovery/prompts/proactivity.txt`

```
You are evaluating whether a restaurant discovery response is proactive and helpful.

User Query: {{input}}
Agent Response: {{output}}

Rate proactivity on a scale of 0-1:
- 1.0: Agent suggests alternatives (different times, cuisines, areas), asks clarifying questions, or offers next steps.
- 0.7: Agent addresses the query adequately but doesn't offer proactive help.
- 0.4: Agent responds minimally; missed opportunities to help.
- 0.0: Agent response doesn't acknowledge user needs or offer any guidance.

Consider:
- If the query was ambiguous, did the agent ask clarifying questions?
- If results were limited, did the agent suggest alternatives?
- Did the agent offer to help with next steps (filtering, booking, changing preferences)?
- Is the agent being helpful without being pushy?

Return ONLY a single number between 0 and 1 on the first line.
Then explain your reasoning.
```

### 6.4 Custom Code Scorer: Tool Routing

**File:** `backend/evals/scorers/common/tool_routing.py`

```python
"""Custom code scorer: did the agent call the expected tool?

Deterministic, no LLM call, no cost. Works across all features.
"""

from braintrust import Score

def tool_routing_correctness(
    output: str,
    trace: dict,
    expected_tool: str = "retrieve",
    **kwargs
) -> Score:
    """
    Check: Did the agent call the expected tool?

    Args:
        output: Agent response (not used for this check)
        trace: Trace dict containing tool calls
        expected_tool: Name of the tool that should have been called

    Returns:
        Score: 1.0 if correct tool called, 0.0 otherwise
    """
    tool_calls = trace.get("tool_calls", [])

    # Check if expected tool was called
    called_tools = [call.get("name") for call in tool_calls]
    tool_called = expected_tool in called_tools

    return Score(
        name="Tool Routing",
        score=1.0 if tool_called else 0.0,
        metadata={
            "expected_tool": expected_tool,
            "tools_called": called_tools,
        }
    )
```

### 6.5 Custom Code Scorer: Data Privacy

**File:** `backend/evals/scorers/common/data_privacy.py`

```python
"""Custom code scorer: does the response leak PII or other users' data?

Applies to ALL 5 features. Deterministic, no LLM call.
"""

import re
from braintrust import Score

def data_privacy_scorer(output: str, **kwargs) -> Score:
    """
    Check: Does output contain PII or other users' reservation data?

    Forbidden patterns:
      - Booking IDs (B-123, booking_ABC)
      - User IDs (user_xyz, userId:123)
      - Email addresses
      - Phone numbers
      - Other reservation details for other users

    Returns:
        Score: 1.0 if no PII detected, 0.0 if any PII found
    """
    forbidden_patterns = [
        r"booking[_-]?[A-Z0-9]+",        # booking IDs
        r"user[_-]?[a-z0-9]+",          # user IDs
        r"userId[:\s][a-z0-9]+",        # variations
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # emails
        r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",  # phone numbers
        r"\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}",  # card numbers
    ]

    for pattern in forbidden_patterns:
        if re.search(pattern, output, re.IGNORECASE):
            return Score(
                name="Data Privacy",
                score=0.0,
                metadata={"violation": f"Pattern '{pattern}' detected in output"}
            )

    return Score(
        name="Data Privacy",
        score=1.0,
        metadata={"status": "no_pii_detected"}
    )
```

---

## 7. Shared Scorers for Booking Operations

### 7.1 Booking Operations Scorers (Future, Used by Reservations/Cancellations/Updates)

**File:** `backend/evals/scorers/common/booking_operations.py`

```python
"""Shared scorers for booking operations (Reservations, Cancellations, Updates).

These scorers are parameterized and reusable across all booking operation features.
Built from first principles: DRY, parameterized, testable.
"""

from braintrust import Score

def user_confirmation_required(
    output: str,
    trace: dict,
    **kwargs
) -> Score:
    """
    Check: Did the agent explicitly ask for user confirmation before taking action?

    Applies to: Reservations, Cancellations, Updates

    Returns: 1.0 if confirmation asked, 0.0 otherwise
    """
    # Check trace for confirmation prompt pattern
    # Implementation: look for patterns like "confirm", "approve", "proceed", etc.
    pass

def correct_tool_called(
    output: str,
    trace: dict,
    expected_tool: str,
    **kwargs
) -> Score:
    """
    Check: Did the agent call the expected tool?

    Applies to: Reservations (create_booking), Cancellations (delete_booking), Updates (update_booking)

    Args:
        expected_tool: Name of tool that should be called (parameterized)

    Returns: 1.0 if correct tool called, 0.0 otherwise
    """
    tool_calls = trace.get("tool_calls", [])
    called_tools = [call.get("name") for call in tool_calls]
    tool_called = expected_tool in called_tools

    return Score(
        name=f"Tool Routing ({expected_tool})",
        score=1.0 if tool_called else 0.0,
        metadata={"expected": expected_tool, "actual": called_tools}
    )

def no_action_without_consent(
    output: str,
    trace: dict,
    **kwargs
) -> Score:
    """
    Check: Did the agent never act without explicit user consent?

    Applies to: Reservations, Cancellations, Updates

    Returns: 1.0 if no unauthorized actions, 0.0 if action taken without consent
    """
    # Cross-check: did agent ask for confirmation AND did user consent?
    pass
```

---

## 8. Integration with Backend & Tracing

### 8.1 Data Flow

```
User Query
    ↓
[Backend POST /chat endpoint]
    ↓
Strands Agent (with Braintrust tracing via instrumentation.py)
    ↓
[Agent calls retrieve tool, synthesizes response]
    ↓
Braintrust automatically captures:
    - input (user query)
    - output (agent response)
    - trace spans (tool calls, context retrieved)
    - metadata
    ↓
[Offline eval reads trace data]
    ↓
Task Function: calls agent, captures output + trace context
    ↓
Scorers evaluate using:
    - input: from test case
    - output: from agent response
    - context: from trace (retrieved documents)
    - trace: full trace dict (tool calls, etc.)
    ↓
Results logged to Braintrust platform
```

### 8.2 Task Function for Discovery Eval

**File:** `backend/evals/braintrust/discovery.py` (excerpt)

```python
async def discovery_task(input_data: dict, hooks=None) -> dict:
    """
    Task function: runs the agent and captures trace context.

    Args:
        input_data: {"input": user query string}
        hooks: Braintrust hooks for attaching metadata

    Returns:
        dict with: output (response), context (retrieved docs), trace data
    """
    from app.agent.core import agent

    query = input_data["input"]

    # Capture trace during agent execution
    trace_data = {}

    async for event in agent.stream_async(messages=[{"role": "user", "content": query}]):
        if event.get("type") == "tool_call":
            if event.get("tool_name") == "retrieve":
                trace_data["tool_calls"] = event.get("calls", [])
                trace_data["retrieved_context"] = event.get("results", [])

    # Return structured output for scorers
    return {
        "output": agent.last_response,
        "context": "\n".join(trace_data.get("retrieved_context", [])),
        "trace": trace_data,
    }
```

---

## 9. Implementation Roadmap

### Phase 1: Architecture & File Setup (30 minutes)

**Deliverables:**
- Create folder structure
- Create placeholder files with docstrings

**Steps:**
```bash
# Create directories
mkdir -p backend/evals/cases
mkdir -p backend/evals/braintrust
mkdir -p backend/evals/scorers/{common,discovery,reservations,cancellations,updates,support}
mkdir -p backend/evals/scorers/discovery/prompts

# Create placeholder files (with docstrings, no implementation yet)
touch backend/evals/cases/{__init__,discovery,reservations,cancellations,updates,support,common}.py
touch backend/evals/braintrust/{__init__,discovery,reservations,cancellations,updates,support}.py
touch backend/evals/scorers/__init__.py
touch backend/evals/scorers/{common,discovery}/{__init__,README}.md
touch backend/evals/scorers/discovery/{rag_quality,agent_helpfulness,agent_proactivity}.py
touch backend/evals/scorers/common/{booking_operations,tool_routing,data_privacy}.py
touch backend/evals/scorers/discovery/prompts/{helpfulness,proactivity}.txt
```

**Success criteria:** File structure matches spec, all files have docstrings.

### Phase 2: Test Cases (1.5 hours)

**File:** `backend/evals/cases/discovery.py`

**Steps:**
1. Import `EvalCase` from `evals.cases.common`
2. Define 16-18 test cases with:
   - Unique `id` for each
   - `input` (user query)
   - `expected` (rubric dict with `should_call` and `description`)
   - `metadata` (query_type, difficulty, expected_tools, tags)

**Example structure:**
```python
DISCOVERY_CASES = [
    EvalCase(id="discovery-basic-01", input="...", expected={...}, metadata={...}),
    EvalCase(id="discovery-basic-02", input="...", expected={...}, metadata={...}),
    # ... 5 basic, 5 filtered, 3 ambiguous, 2-3 edge/boundary
]
```

**Success criteria:** 16-18 test cases, each with valid id/input/expected/metadata.

### Phase 3: Scorer Implementation (1.5 hours)

**Files:**
- `backend/evals/scorers/discovery/rag_quality.py` — composite scorer (returns 3 scores)
- `backend/evals/scorers/discovery/agent_helpfulness.py` — LLM-as-judge
- `backend/evals/scorers/discovery/agent_proactivity.py` — LLM-as-judge
- `backend/evals/scorers/common/tool_routing.py` — custom code
- `backend/evals/scorers/common/data_privacy.py` — custom code
- `backend/evals/scorers/discovery/prompts/*.txt` — prompt templates

**Steps:**
1. Implement each scorer function with proper docstrings
2. Implement prompt templates
3. Test scorers on sample outputs (manual testing)

**Success criteria:** All scorers callable, prompts readable, no obvious errors.

### Phase 4: Eval Runner & First Run (1 hour)

**File:** `backend/evals/braintrust/discovery.py`

**Steps:**
1. Create eval runner that:
   - Loads dataset via `init_dataset()`
   - Defines task function (calls agent, captures trace)
   - Wires all 6 scorers
   - Runs `Eval()` with metadata
2. Run eval locally: `uv run braintrust eval --env-file .env evals/braintrust/discovery.py`
3. Review results, identify low-scoring cases

**Success criteria:** Eval runs end-to-end, produces scores, identifies failure patterns.

---

## 10. Scalability & Future Features

### 10.1 Adding Reservations, Cancellations, Updates

Once Discovery POC is complete, each new feature follows the same pattern:

1. **Add test cases** → `backend/evals/cases/{reservations,cancellations,updates}.py`
2. **Create feature-specific scorers** → `backend/evals/scorers/{reservations,cancellations,updates}/`
3. **Reuse shared scorers** → `booking_operations.py`, `data_privacy.py`
4. **Create eval runner** → `backend/evals/braintrust/{reservations,cancellations,updates}.py`
5. **Run eval** → baseline, iterate, add cases

**Shared scorers grow as patterns emerge:**
- `user_confirmation_required` — applies to all booking operations
- `correct_tool_called(expected_tool)` — parameterized across all features
- `data_privacy` — applies to all 5 features

### 10.2 Integration with CI/CD

Future: Add to GitHub Actions workflow:
```yaml
- name: Run Discovery Evals
  run: uv run braintrust eval --env-file .env evals/braintrust/discovery.py

- name: Run Booking Operations Evals
  run: |
    uv run braintrust eval --env-file .env evals/braintrust/reservations.py
    uv run braintrust eval --env-file .env evals/braintrust/cancellations.py
    uv run braintrust eval --env-file .env evals/braintrust/updates.py
```

---

## 11. Design Review Checklist

- ✓ **Feature definitions clear** — acceptance criteria spelled out for Discovery
- ✓ **Test case structure consistent** — all cases follow EvalCase pattern
- ✓ **Scorers well-motivated** — each scorer has a clear "why"
- ✓ **Shared vs. feature-specific clear** — common scorers in `common/`, features in their folders
- ✓ **File paths explicit** — every implementation step has a file path
- ✓ **4-hour timeline realistic** — phases broken down, 30m + 1.5h + 1.5h + 1h
- ✓ **Scalable to 5 features** — architecture handles growth without refactoring
- ✓ **No placeholders** — all sections have concrete examples or decisions
- ✓ **Scope clear** — Discovery is POC, Reservations/Cancellations/Updates deferred but architected

---

## Appendix A: Example Test Cases (Discovery)

### Basic Search
```python
EvalCase(
    id="discovery-basic-01",
    input="What restaurants do you have?",
    expected={
        "should_call": ["retrieve"],
        "description": "Call retrieve with a broad query. Return all available restaurants with names, cuisines, and hours."
    },
    metadata={
        "query_type": "basic_search",
        "difficulty": "easy",
        "expected_tools": ["retrieve"],
        "category": "discovery",
        "tags": ["all_restaurants"]
    }
)
```

### Filtered Search
```python
EvalCase(
    id="discovery-filtered-01",
    input="Show me Italian restaurants downtown",
    expected={
        "should_call": ["retrieve"],
        "description": "Call retrieve with 'Italian restaurants downtown'. Return 2-5 Italian restaurants with name, cuisine, hours, location."
    },
    metadata={
        "query_type": "filtered_search",
        "difficulty": "medium",
        "expected_tools": ["retrieve"],
        "category": "discovery",
        "tags": ["cuisine_filter", "location_filter"]
    }
)
```

### Ambiguous Query
```python
EvalCase(
    id="discovery-ambiguous-01",
    input="Something nice for a date",
    expected={
        "should_call": ["retrieve"],
        "description": "Query is ambiguous (no cuisine/location). Agent should either ask clarifying questions OR call retrieve with a reasonable guess. Response should acknowledge ambiguity."
    },
    metadata={
        "query_type": "ambiguous",
        "difficulty": "hard",
        "expected_tools": ["retrieve"],
        "category": "discovery",
        "tags": ["ambiguous_query", "requires_clarification"]
    }
)
```

---

## Appendix B: Scoring Thresholds by Tier

### Tier 1: Hard Stops (Pass = 1.0, Fail = 0.0)
- Tool Routing: must call `retrieve`
- Data Privacy: no PII leakage

### Tier 2: Critical (Pass ≥ 0.8)
- Faithfulness: answer supported by context

### Tier 3: Standard (Pass ≥ 0.7)
- ContextRelevancy: context relevant to query
- AnswerRelevancy: answer relevant to question
- Agent Helpfulness: response is helpful and clear

### Tier 4: Nice-to-Have (Pass ≥ 0.6)
- Agent Proactivity: offers alternatives, clarifications, or next steps

**Overall test result:** PASS if all Tier 1 = 1.0, Tier 2 ≥ 0.8, Tier 3 ≥ 0.7. Tier 4 can dip to 0.6.

---

**End of Specification**
