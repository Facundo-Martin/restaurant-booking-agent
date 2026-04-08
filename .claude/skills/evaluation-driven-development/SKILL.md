---
name: evaluation-driven-development
description: |
  Design and implement evaluations for Strands Agents using Evaluation Driven Development (EDD).

  This skill guides you through building a comprehensive evaluation suite progressively, starting
  with architectural decisions (what to evaluate and why), then implementing evaluators step-by-step
  (OutputEvaluator → ToolUsageEvaluator → TraceEvaluators → Advanced features).

  Use this skill whenever you need to: build an evaluation suite for an agent feature, design what
  evaluations to run first, implement evaluators following best practices, set up async evaluation
  pipelines, or understand evaluation results. This covers discovery evaluations, trajectory testing,
  helpfulness scoring, tool accuracy, and custom domain-specific evaluators.
compatibility: Requires Strands Agents SDK (strands-agents-evals, strands-agents)
---

# Evaluation Driven Development for Strands Agents

Design and build evaluation suites progressively, from architecture to implementation.

## Process Overview

**MUST** work through these phases in order. Each phase MUST be completed before moving forward:

```
PHASE 1: Architecture Design (MUST DO)
  ├─ Explore agent/feature context
  ├─ Ask: RAG/KB dependency? Security/PII? Single or Multi-agent?
  ├─ Identify evaluation goals and constraints
  ├─ Choose evaluation strategy (progressive building)
  └─ Get approval before coding

PHASE 2: Implementation (Progressive — MUST follow this order)
  ├─ Phase 2a: OutputEvaluator (MUST DO — foundation)
  ├─ Phase 2b: TrajectoryEvaluator (IF agent.uses_tools THEN MUST DO)
  ├─ Phase 2c: HelpfulnessEvaluator (IF agent.is_multiturn THEN MUST DO)
  ├─ Phase 2d: Scripts & Async Execution (SHOULD DO for ≥5 cases)
  ├─ Phase 2e: Rate Limiting & Results Handling (SHOULD DO for production)
  └─ Phase 2f: Advanced (MAY DO after 2a–2e passing)

PHASE 3: Validation & Deployment (MUST DO)
  ├─ Run evaluation suite end-to-end
  ├─ Verify results & logging
  └─ Document for team
```

**Constraint Key:**
- **MUST DO**: Cannot skip without explicit reason. Blocks progression.
- **SHOULD DO**: Strongly recommended for your scenario.
- **MAY DO**: Optional; add only if needed.

---

## PHASE 1: Architecture Design

### Step 1: Explore Context & Clarify Critical Requirements

**Read and understand:**
- **Agent definition**: What does the agent do? What are its tools?
- **Feature being evaluated**: What capability are you testing? (e.g., discovery, booking, multi-turn conversation)
- **Success criteria**: How do you know the agent is working well?
- **Constraints**: API rate limits? Budget? Deployment environment?

**MUST ask these three critical factors (ask if not explicitly mentioned):**

1. **RAG/Knowledge Base Dependency**
   - Question: "Does the agent use retrieval-augmented generation (RAG) or a knowledge base?"
   - IF YES THEN: evaluators MUST include **Faithfulness** (does it stick to context?) and **Context Relevancy** (was the right context retrieved?)
   - IF NO THEN: focus SHOULD be on output quality and tool usage only; Faithfulness evaluator MAY be skipped

2. **Security & Privacy Concerns**
   - Question: "Are there sensitive data, PII, or security guardrails involved?"
   - IF YES THEN: MUST add **Safety/Guardrail Evaluators** to catch hallucinations, PII leakage, policy violations (may need custom evaluator in Phase 2f)
   - IF NO THEN: standard output quality evaluation is SUFFICIENT; safety evaluators MAY be skipped

3. **System Architecture**
   - Question: "Is this a single-agent system or multi-agent (agent-to-agent)?"
   - IF SINGLE THEN: follow standard evaluation path (2a → 2b if tools → 2c if multi-turn)
   - IF MULTI-AGENT THEN: MUST add complexity for cross-agent communication, handoffs, state passing; MUST implement custom evaluators in Phase 2f for agent coordination (handoff validation, state isolation, error propagation)

### Step 2: Define Evaluation Goals
Answer these questions:
1. **Output quality**: Is the agent's final response correct, helpful, relevant?
2. **Tool usage**: Is the agent selecting the right tools and calling them correctly?
3. **Trajectory/reasoning**: Is the agent taking logical steps? (multi-turn only)
4. **Domain-specific**: Any special requirements? (e.g., no hallucinations, follow safety guardrails)

### Step 3: Choose Progressive Strategy

You MUST build evaluations in phases. **Do not skip or reorder phases** — each is a foundation for the next:

- **Phase 2a (Foundation) — MUST DO**: Start with `OutputEvaluator` — simplest, most critical. Defines "does the response quality meet expectations?" MUST achieve ≥80% pass rate before Phase 2b.

- **Phase 2b (Tool Accuracy) — IF/THEN**: IF agent uses tools THEN MUST add `TrajectoryEvaluator`. Tests "did the agent call the right tools with correct parameters?"

- **Phase 2c (Multi-Turn) — IF/THEN**: IF agent handles multi-turn conversations THEN MUST add `HelpfulnessEvaluator` + trace collection. Tests "was the response helpful across the conversation?"

- **Phase 2d–2e (Production Infrastructure) — SHOULD DO**: Once 2a–2c complete, set up async execution, rate limiting, JSON logging for scaling.

- **Phase 2f (Advanced) — MAY DO**: Only after Phase 2a–2e all passing — custom evaluators for domain-specific needs, experiment generation, multi-agent coordination tests.

**Why this order?**
- Phase 2a establishes baseline correctness
- Phase 2b validates tool selection (irrelevant if no tools)
- Phase 2c validates conversation flow (irrelevant if single-turn)
- Skipping to advanced evaluators without foundation makes debugging impossible

### Step 4: Design Test Cases
Create a small set of representative test cases (5–10 initially):
- **Baseline cases**: Happy path, normal usage
- **Edge cases**: Boundary conditions, unusual inputs
- **Negative cases**: What should fail gracefully?

Test cases should be `Case` objects with:
```python
Case(
    name="descriptive-name",
    input="user query",
    expected_output="what a good response looks like",
    expected_trajectory=["tool_1", "tool_2"] if applicable
)
```

### Step 5: Get Approval
Before writing code, confirm:
- [ ] Agent/feature context is clear
- [ ] Evaluation goals are defined
- [ ] Progressive strategy is approved (which phases will you implement?)
- [ ] Test cases are representative

---

## PHASE 2: Implementation (Progressive)

### PHASE 2a: OutputEvaluator (ALWAYS START HERE)

This is your foundation. Every agent evaluation starts with "is the response good?"

**Step 1: Define Rubric**
Create a clear rubric for what "good" means:

```python
# Example rubric
output_rubric = """
Score 1.0 if the response:
- Directly answers the user's question
- Is factually accurate
- Is well-structured and clear

Score 0.5 if:
- The response partially answers the question
- Contains minor inaccuracies
- Needs minor clarification

Score 0.0 if:
- The response misses the main question
- Contains major inaccuracies
- Is unclear or unhelpful
"""
```

**Step 2: Create Experiment**
```python
from strands_evals import Case, Experiment, OutputEvaluator

cases = [
    Case(name="case-1", input="...", expected_output="..."),
    # ... more cases
]

evaluator = OutputEvaluator(rubric=output_rubric)
experiment = Experiment(cases=cases, evaluator=evaluator)

# Task function: how to run your agent
def task_function(case: Case) -> dict:
    result = agent.invoke(case.input)
    return {"output": str(result)}

# Run synchronously (small test sets)
reports = experiment.run_evaluations(task_function)
for report in reports:
    report.run_display()
```

**Step 3: Review Results**
- Check individual case scores and judge reasoning
- Identify patterns in failures
- If ≥80% pass: proceed to Phase 2b/2c
- If <80% pass: fix agent or refine rubric, rerun Phase 2a

**Before Moving to Phase 2b — Acceptance Criteria**

Verification MUST-Pass (blocks progression):
- [ ] Pass rate ≥80% (minimum viable quality)
- [ ] All test cases run without syntax errors
- [ ] Rubric includes explicit scores (1.0, 0.5, 0.0)

Verification SHOULD-Pass (strongly recommended):
- [ ] Test cases represent baseline + edge + negative scenarios
- [ ] Rubric has clear justification per score level
- [ ] Judge reasoning is specific and actionable

Verification MAY-Pass (nice-to-have):
- [ ] Per-case reasoning logged to file
- [ ] Results archived for comparison across iterations

---

### PHASE 2b: TrajectoryEvaluator (Tool Usage)

**IF agent.uses_tools THEN you MUST do Phase 2b.**
**ELSE you MAY SKIP to Phase 2c or Phase 2d.**

Tests "did the agent pick the right tools and call them correctly?"

**Step 1: Extract Tool Usage**
Use `tools_use_extractor` to avoid context overflow:

```python
from strands_evals.extractors import tools_use_extractor

def task_function(case: Case) -> dict:
    result = agent.invoke(case.input)
    tool_calls = tools_use_extractor.extract_agent_tools_used(agent.messages)
    return {
        "output": str(result),
        "trajectory": tool_calls
    }
```

**Step 2: Define Expected Trajectories**
Add to test cases:

```python
Case(
    name="search-and-book",
    input="Find restaurants in NYC and book one",
    expected_output="...",
    expected_trajectory=["search_restaurants", "get_details", "book_reservation"]  # in order
)
```

**Step 3: Create Evaluator**
```python
from strands_evals import TrajectoryEvaluator

evaluator = TrajectoryEvaluator(
    rubric="Verify the agent selected appropriate tools and called them in logical order"
)

# Re-use same cases + experiment
experiment = Experiment(
    cases=cases,
    evaluator=[OutputEvaluator(...), evaluator]  # run both
)
```

**Step 4: Review Results**
- Did agent select correct tools?
- Was ordering logical?
- Any missing or extraneous tool calls?

**Before Moving to Phase 2c — Acceptance Criteria**

Verification MUST-Pass (blocks progression):
- [ ] Tool selection matches expected trajectories in ≥80% of cases
- [ ] Pass rate ≥80% across both OutputEvaluator AND TrajectoryEvaluator
- [ ] No syntax errors in tool extraction

Verification SHOULD-Pass (strongly recommended):
- [ ] Tool ordering is logical and defensible
- [ ] Parameter correctness evaluated (not just tool name)
- [ ] Judge reasoning explains tool selection rationale

Verification MAY-Pass (nice-to-have):
- [ ] Tools called with exact expected parameters
- [ ] Results logged with trajectory details

---

### PHASE 2c: HelpfulnessEvaluator + Traces (Multi-Turn)

**IF agent.is_multiturn THEN you MUST do Phase 2c.**
**ELSE you MAY SKIP to Phase 2d.**

**Step 1: Collect Traces with Session ID**
Critical: include session attributes to prevent span mixing:

```python
from opentelemetry import trace
from strands_evals import HelpfulnessEvaluator
from strands_evals.mappers import StrandsInMemorySessionMapper

def async_task_function(case: Case) -> dict:
    # Set session ID in trace context
    span = trace.get_current_span()
    span.set_attribute("gen_ai.conversation.id", case.id)
    span.set_attribute("session.id", case.id)

    # Run agent multi-turn
    result = await agent.invoke_async(case.input)

    # Extract conversation history + trace
    mapper = StrandsInMemorySessionMapper()
    session = mapper.map_to_session(spans, session_id=case.id)

    return {
        "output": str(result),
        "trajectory": session  # full conversation trace
    }
```

**Step 2: Create Evaluator**
```python
evaluator = HelpfulnessEvaluator()  # uses 7-point scale

experiment = Experiment(
    cases=cases,
    evaluators=[OutputEvaluator(...), TrajectoryEvaluator(...), evaluator]
)
```

**Before Moving to Phase 2d — Acceptance Criteria**

Verification MUST-Pass (blocks progression):
- [ ] Traces include session IDs (no span mixing across conversations)
- [ ] HelpfulnessEvaluator runs without errors
- [ ] Pass rate ≥80% across all evaluators (Output + Trajectory + Helpfulness)

Verification SHOULD-Pass (strongly recommended):
- [ ] Multi-turn conversations flow logically with context continuity
- [ ] Helpfulness scores correlate with agent improvements
- [ ] Session mapper correctly extracts full conversation history

Verification MAY-Pass (nice-to-have):
- [ ] Span attributes logged for debugging
- [ ] Turn-by-turn interaction records archived

---

### PHASE 2d: Scripts & Async Execution

**SHOULD DO once Phases 2a–2c pass.** Set up proper execution infrastructure.
(Skip only if running <5 test cases in a development environment.)

**Step 1: Create eval_discovery.py**
```python
import asyncio
from strands_evals import Experiment, Case
from strands_evals import OutputEvaluator, TrajectoryEvaluator, HelpfulnessEvaluator

# Define cases
cases = [...]  # from Phase 1

# Define evaluators
evaluators = [
    OutputEvaluator(rubric="..."),
    TrajectoryEvaluator(rubric="..."),
    HelpfulnessEvaluator()
]

# Task function
async def eval_discovery(case: Case) -> dict:
    result = await agent.invoke_async(case.input)
    return {"output": str(result)}

# Run async (faster for many cases)
async def main():
    experiment = Experiment(cases=cases, evaluators=evaluators)
    reports = await experiment.run_evaluations_async(eval_discovery)

    for report in reports:
        print(report.case_results)
        report.display()

if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: Add to package.json**
```json
{
  "scripts": {
    "eval:discovery": "cd backend && uv run python evals/discovery.py",
    "eval:discovery:async": "cd backend && uv run python evals/discovery.py --async",
    "eval:discovery:watch": "nodemon --exec 'npm run eval:discovery'"
  }
}
```

**Step 3: Run**
```bash
npm run eval:discovery          # single run
npm run eval:discovery:async    # async (recommended)
npm run eval:discovery:watch    # watch for changes
```

---

### PHASE 2e: Rate Limiting & Understanding Results

**SHOULD DO for production; MAY SKIP for development-only evaluations.**

As you scale to more test cases, MUST handle rate limits and logging.

**Step 1: Async with Concurrency Control**
```python
# Limit concurrent evaluations to avoid rate limits
reports = await experiment.run_evaluations_async(
    eval_discovery,
    max_workers=3  # adjust based on rate limits
)
```

**Step 2: Understand Results**
```python
for report in reports:
    # Per-case details
    for result in report.case_results:
        print(f"Case: {result.case.name}")
        print(f"Scores: {result.scores}")
        print(f"Pass: {result.test_passed}")
        print(f"Reasoning: {result.reasoning}\n")

    # Summary stats
    print(f"Pass rate: {report.pass_rate}")
    print(f"Avg score: {report.average_score}")
```

**Step 3: Log Results to File**
```python
import json

results_log = {
    "timestamp": datetime.now().isoformat(),
    "pass_rate": report.pass_rate,
    "average_score": report.average_score,
    "cases": [
        {
            "name": result.case.name,
            "scores": result.scores,
            "passed": result.test_passed
        }
        for result in report.case_results
    ]
}

with open("eval_results.json", "w") as f:
    json.dump(results_log, f, indent=2)
```

---

### PHASE 2f: Advanced Features (Optional)

**MAY DO only after Phases 2a–2e are all passing.**

**IF custom_needs THEN implement custom evaluators or multi-agent coordination tests.**
**ELSE Phase 2e is sufficient — do not add Phase 2f.**

**Custom Evaluators**
If you need domain-specific logic not covered by built-in evaluators:

```python
from strands_evals import Evaluator, EvaluationOutput

class SafetyEvaluator(Evaluator):
    """Custom evaluator for safety guidelines."""

    async def eval_async(self, case: Case, output: str) -> EvaluationOutput:
        # Your custom logic
        has_harmful_content = check_safety(output)

        return EvaluationOutput(
            score=0.0 if has_harmful_content else 1.0,
            test_passed=not has_harmful_content,
            reasoning="Response passed safety check"
        )

# Use it
evaluator = SafetyEvaluator()
experiment = Experiment(cases=cases, evaluators=[..., evaluator])
```

**Automated Experiment Generation**
If you're unsure what test cases to create:

```python
from strands_evals import ExperimentGenerator, OutputEvaluator

generator = ExperimentGenerator()
experiment = await generator.from_context_async(
    context="Agent discovers restaurants based on user preferences",
    num_cases=10,
    evaluator=OutputEvaluator(rubric="...")
)

# Save for reuse
experiment.to_file("generated_cases")
```

---

## PHASE 3: Validation & Deployment

### Step 1: Run Full Suite (MUST DO)
```bash
npm run eval:discovery:async
```

Verification MUST-Pass:
- [ ] All test cases complete without crashing
- [ ] No rate limit errors (adjust `max_workers` if needed)
- [ ] Results logged to file with ISO timestamp
- [ ] Pass rates meet expectations (≥80% per phase)

Verification SHOULD-Pass:
- [ ] Per-case reasoning is clear and specific
- [ ] Results include execution time metadata
- [ ] Failures have actionable debugging info

### Step 2: Review & Iterate (SHOULD DO)
- MUST: Compare results across iterations (save each run with timestamp)
- SHOULD: Adjust agent/evaluators based on failures
- SHOULD: Rerun Phases 2a–2e as needed for improvement

### Step 3: Documentation (SHOULD DO)
Create `EVALUATION.md` in project root:

```markdown
# Evaluation Suite: Discovery Feature

## Test Cases
- [list of test cases and what they verify]

## Evaluators
- OutputEvaluator: response quality
- TrajectoryEvaluator: tool usage
- HelpfulnessEvaluator: multi-turn helpfulness

## Running Evaluations
\`\`\`bash
npm run eval:discovery
\`\`\`

## Results
- Latest results in: `eval_results.json`
- Target pass rate: 85%+
```

---

## Best Practices

1. **Respect phase progression (MUST)** — do not skip Phase 2a, 2b, or 2c. Each is foundational. Phase 2d–2f are SHOULD/MAY, not MUST.

2. **Start simple, build progressively (MUST)** — don't jump to custom evaluators before output evaluation works. Phase 2a MUST pass before Phase 2b.

3. **Keep test cases lean (SHOULD)** — 5–10 cases per phase initially; expand after validation. Baseline + edge + negative categories SHOULD be represented.

4. **Use async for ≥5 cases (SHOULD)** — `run_evaluations_async()` with `max_workers` control. Sync execution becomes slow at scale.

5. **Version your rubrics (SHOULD)** — document why each criterion exists; archive rubrics with results for comparison.

6. **Log everything (SHOULD)** — timestamp, pass rates, case names for trend tracking. JSON logging enables historical analysis.

7. **Rate limiting is ok (SHOULD)** — use `max_workers` to stay within API limits. Better to run 3 concurrent than hit rate limit and restart.

8. **Reuse experiments (MAY)** — save to JSON, share with team, version in git. Experiment serialization enables reproducibility.

9. **Understand RFC 2119 (informational)** — this skill uses MUST/SHOULD/MAY language to distinguish blocking constraints from recommendations.

---

## Quick Reference: Which Evaluator When?

| Evaluator | When to Use | Example |
|-----------|------------|---------|
| OutputEvaluator | Always, first | Is response correct/helpful? |
| TrajectoryEvaluator | If agent uses tools | Did agent pick the right tool? |
| HelpfulnessEvaluator | Multi-turn conversations | Was response helpful over conversation? |
| Custom Evaluator | Domain-specific needs | Safety, compliance, guardrails |
| ExperimentGenerator | Uncertain about test cases | Auto-generate diverse test cases |

---

## RFC 2119 Constraint Language

This skill uses RFC 2119 keywords to distinguish between blocking constraints and recommendations:

| Keyword | Meaning | Impact on Progression |
|---------|---------|----------------------|
| **MUST / MUST NOT** | Requirement — non-negotiable. Violating this blocks you. | Blocks progression to next phase |
| **SHOULD / SHOULD NOT** | Strong recommendation — follow unless you have good reason not to. | Recommend but doesn't block |
| **MAY** | Optional — do this if your scenario requires it. | Truly optional |

**Examples:**
- "MUST complete Phase 2a with ≥80% pass rate before Phase 2b" — you cannot progress without this.
- "SHOULD use async for ≥5 cases" — recommended for performance, but sync is acceptable for small test sets.
- "MAY archive results for trend tracking" — nice-to-have but not required.

---

## Integration with Writing Plans

Once your evaluation suite is designed, use the **writing-plans** skill to create an implementation roadmap for the agent feature itself, informed by what you learned from evaluation design.
