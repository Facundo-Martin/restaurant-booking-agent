# Restaurant Booking Agent — Evaluation Suite (Strands Evals)

Comprehensive evaluation framework for the restaurant booking agent using **Evaluation Driven Development (EDD)** with Strands Evals SDK.

---

## Architecture

**Single Agent, Multi-Turn:**
- One agent handles both discovery (finding restaurants) and booking (making reservations)
- Multi-turn conversations with context continuity
- Bedrock Knowledge Base for restaurant data
- Tools: `search_restaurants`, `create_booking`, `get_restaurant_details`
- Security: Real user data with PII concerns (phone, email, addresses)

---

## Evaluation Phases (EDD Methodology)

Implement progressively, completing each phase before moving forward:

### PHASE 2a: OutputEvaluator ✅ IMPLEMENTED
**Status:** Ready to run

Evaluates: Does the agent produce correct, helpful responses?

**Test Cases:** 7 (3 baseline, 2 edge, 2 negative)
- Baseline: simple discovery, valid booking, discovery with filters
- Edge: vague query, missing booking info, no results
- Negative: recovery from error

**Rubric:** Explicit scores (1.0 = excellent, 0.5 = partial, 0.0 = failing)

**Run:**
```bash
npm run eval:strands:discovery-booking
```

**Expected Output:**
- Per-case scores and reasoning
- Summary: pass rate, average score
- JSON log: `eval_results_phase2a.json`
- Target: ≥80% pass rate before Phase 2b

---

### PHASE 2b: TrajectoryEvaluator 🔄 TODO
**Status:** Next phase after 2a passes

Evaluates: Does the agent call tools correctly and in the right order?

**Implementation needed:**
1. Define `expected_trajectory` in test cases
   ```python
   Case(
       name="discovery-then-book",
       input="Find Italian restaurants then book Mario's for 2 at 7 PM",
       expected_trajectory=["search_restaurants", "create_booking"]
   )
   ```

2. Create TrajectoryEvaluator with tool rubric
3. Run both OutputEvaluator + TrajectoryEvaluator together
4. Acceptance: ≥80% pass on both evaluators

---

### PHASE 2c: HelpfulnessEvaluator 🔄 TODO
**Status:** After 2b passes

Evaluates: Is the agent helpful across the multi-turn conversation?

**Implementation needed:**
1. Add session ID tracing to prevent span mixing
2. Use `StrandsInMemorySessionMapper` to extract conversation history
3. Create HelpfulnessEvaluator (7-point Likert scale)
4. Test multi-turn scenarios (agent remembers preferences, context)

---

### PHASE 2d-2e: Scripts & Rate Limiting 🔄 TODO
**Status:** After 2c passes

**Implementation needed:**
1. Add async execution with `max_workers=3`
2. Structured JSON logging with timestamps
3. npm scripts for watch mode and CI integration

---

### PHASE 2f: Custom Evaluators (Optional) 🔄 TODO
**Status:** After 2d-2e or as needed

**Recommended:** PII Detection Evaluator
- Ensures phone numbers, emails, addresses are masked in output
- Critical for security and compliance
- Custom implementation inheriting from `Evaluator` base class

---

## Quick Start

### Run Phase 2a Only
```bash
# Single run (sync)
npm run eval:strands:discovery-booking

# Async with rate limiting
npm run eval:strands:discovery-booking:async
```

### Before Moving Forward
Check acceptance criteria in the output:
- [ ] Pass rate ≥80%?
- [ ] All test cases run without errors?
- [ ] Rubric has explicit scores (1.0, 0.5, 0.0)?

If YES → proceed to Phase 2b
If NO → refine agent or rubric, rerun Phase 2a

---

## File Structure

```
backend/evals/
├── README.md (this file)
├── discovery_booking.py (Phase 2a implementation)
├── eval_results_phase2a.json (output log)
└── (Phase 2b-2f files to be added)
```

---

## Integration with Agent

The evaluation suite expects:
- Agent accessible via `from app.agent import create_agent()`
- Agent has `invoke_async(input: str)` method
- Agent returns structured response with text content

Current placeholder in `discovery_booking.py` — replace with actual agent once available.

---

## EDD Methodology

See `.claude/skills/evaluation-driven-development/SKILL.md` for full guidance on:
- Architectural decisions (RAG/KB, security, single/multi-agent)
- Phase progression (why each phase builds on the previous)
- Test case design (baseline, edge, negative)
- Best practices (async, rate limiting, versioning)
- RFC 2119 constraints (MUST/SHOULD/MAY)

---

## Next Steps

1. ✅ Phase 2a: OutputEvaluator (ready to run)
2. 🔄 Phase 2b: TrajectoryEvaluator (next after 2a passes)
3. 🔄 Phase 2c: HelpfulnessEvaluator (after 2b)
4. 🔄 Phase 2d-2e: Production infrastructure (after 2c)
5. 🔄 Phase 2f: Custom evaluators (optional, for PII detection)

---

## References

- **Strands Evals SDK:** https://github.com/strands-agents/evals
- **EDD Skill:** `.claude/skills/evaluation-driven-development/SKILL.md`
- **Agent Code:** `backend/app/agent.py`
