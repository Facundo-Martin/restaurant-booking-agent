# EDD + TDD Design — Restaurant Booking Agent

**Date:** 2026-03-30
**Branch:** facundomartin98/fac-167-enhance-agent-evals-with-braintrust
**Status:** Approved — proceeding to implementation

---

## Problem

Eval cases were duplicated across 4+ files (`tests/evals/`, `evals/`, `scripts/`). The split between `tests/evals/` (Strands) and `evals/` (Braintrust) was framework-imposed, not domain-driven. Adding a new behavioral contract required editing multiple files. CI ran the same cases twice through two frameworks.

---

## Goals

1. Single source of truth for all eval cases — one line to add a new behavioral contract
2. Clear architectural boundary: data layer has zero framework imports
3. Strands evals for local iteration; Braintrust eval-action for CI experiment tracking
4. PR comments showing score diffs vs baseline on every eval-touching PR
5. Foundation in place for v2 OTel-based evaluators (Faithfulness, ToolParameter)

---

## Out of Scope (v2)

- `FaithfulnessEvaluator` — high value once real KB responses are available in staging; requires OTel + `StrandsInMemorySessionMapper` setup
- `ToolParameterEvaluator` — checks parameter grounding in conversation context; genuinely additive but adds setup complexity
- `ToolSelectionEvaluator` — skip entirely; deterministic `trajectory_scorer.py` is more reliable than LLM-as-judge for our enumerable tool routing rules

---

## Architecture

### Dependency direction

```
cases.py (data, zero imports)
    ↑
    ├── evals/braintrust/eval_output_quality.py
    ├── evals/braintrust/eval_trajectory.py
    ├── evals/strands/test_agent_evals.py
    ├── evals/strands/output_quality_eval.py
    ├── evals/strands/trajectory_eval.py
    └── scripts/create_braintrust_dataset.py
```

`cases.py` imports nothing except `dataclasses`. Framework-specific types (`strands_evals.Case`, Braintrust `Eval`) never appear in it.

---

## File Structure

```
backend/
├── evals/                              ← ALL evals consolidated here
│   ├── cases.py                        ← NEW: source of truth, zero framework imports
│   ├── __init__.py
│   ├── braintrust/                     ← needs BRAINTRUST_API_KEY + AWS creds
│   │   ├── __init__.py
│   │   ├── eval_output_quality.py      ← UPDATE: import from cases.py
│   │   └── eval_trajectory.py          ← UPDATE: import from cases.py
│   ├── strands/                        ← needs AWS creds only
│   │   ├── __init__.py
│   │   ├── test_agent_evals.py         ← UPDATE: import from cases.py
│   │   ├── output_quality_eval.py      ← RENAME from basic_eval.py + import from cases.py
│   │   ├── trajectory_eval.py          ← UPDATE: import from cases.py
│   │   └── otel_scaffold.py            ← REPLACE calculator boilerplate → restaurant agent
│   └── scorers/
│       ├── output_quality_scorer.py    ← unchanged
│       └── trajectory_scorer.py        ← unchanged
├── scripts/
│   └── create_braintrust_dataset.py    ← UPDATE: import from cases.py
└── tests/                              ← unit + integration tests only (no evals)
    ├── conftest.py
    ├── unit/
    └── integration/
```

---

## Data Layer — `evals/cases.py`

```python
from dataclasses import dataclass, field

@dataclass
class EvalCase:
    id: str                      # stable identifier; used as Braintrust dataset record ID
    input: str                   # user message
    expected: str | list[str]    # str → output quality rubric; list[str] → tool trajectory
    metadata: dict = field(default_factory=dict)  # {"category": "...", "eval_type": "..."}

OUTPUT_QUALITY_CASES: list[EvalCase] = [...]   # ~8 cases: clarification, safety, discovery
TRAJECTORY_CASES: list[EvalCase] = [...]       # ~7 cases: discovery, booking flow, off-topic
```

### Adapter patterns (inline at call sites — no named converter functions)

```python
# Braintrust Eval() — drop id (Braintrust assigns its own)
data=[{k: v for k, v in dataclasses.asdict(c).items() if k != "id"} for c in CASES]

# Dataset seeder — all fields (id used for upsert deduplication)
record = dataclasses.asdict(case)

# Strands Case — map field names
Case(name=c.id, input=c.input, expected_output=c.expected, metadata=c.metadata)
```

No converter functions. Each framework adapts inline. `cases.py` stays stable.

---

## Eval Layers

### Layer 1: Braintrust (CI + platform tracking)

**`evals/braintrust/eval_output_quality.py`**
- `Eval("Restaurant Booking — Output Quality", data=[...], task=run_agent, scores=[booking_output_quality_scorer])`
- Scorer: Bedrock Haiku LLM-as-judge via `output_quality_scorer.py`
- Cases: `OUTPUT_QUALITY_CASES` (clarification safety, off-topic rejection, discovery)

**`evals/braintrust/eval_trajectory.py`**
- `Eval("Restaurant Booking — Trajectory", data=[...], task=run_agent_with_trajectory, scores=[trajectory_scorer])`
- Scorer: deterministic `trajectory_scorer.py` (no LLM call — cheaper, faster, more reliable)
- Cases: `TRAJECTORY_CASES` (expected tool sequences per scenario)

### Layer 2: Strands (local iteration)

**`evals/strands/test_agent_evals.py`** — pytest-discoverable (`-m agent`)
- Uses `strands_evals.Experiment` + `OutputEvaluator` / `TrajectoryEvaluator`
- Run locally: `uv run pytest evals/ -m agent -v`
- Does NOT run in CI (covered by Braintrust eval-action)

**`evals/strands/output_quality_eval.py`** — standalone script
- Run locally: `uv run python -u evals/strands/output_quality_eval.py`
- Rich `run_display()` output for prompt iteration debugging

**`evals/strands/trajectory_eval.py`** — standalone script
- Run locally: `uv run python -u evals/strands/trajectory_eval.py`

**`evals/strands/otel_scaffold.py`** — OTel foundation for v2
- Restaurant agent (not calculator) wired with `StrandsEvalsTelemetry` + `StrandsInMemorySessionMapper`
- 2–3 cases using `HelpfulnessEvaluator` as a starting point
- Not run in CI yet; exists as a working v2 starting point
- Run locally: `uv run python -u evals/strands/otel_scaffold.py`

---

## CI Workflow — `evals.yml`

Single step: `braintrustdata/eval-action@v1`

```yaml
- name: Run evaluations
  uses: braintrustdata/eval-action@v1
  with:
    runtime: python
    root: backend
    files: |
      evals/braintrust/eval_output_quality.py
      evals/braintrust/eval_trajectory.py
    api_key: ${{ secrets.BRAINTRUST_API_KEY }}
  env:
    AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
    AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
    AWS_DEFAULT_REGION: us-east-1
    GITHUB_SHA: ${{ github.sha }}
    SST_RESOURCE_Bookings: '{"name":"eval-stub"}'
    SST_RESOURCE_RestaurantKB: '{"id":"eval-stub"}'
    SST_RESOURCE_AgentSessions: '{"name":"eval-sessions"}'
```

**Why not both Strands pytest + Braintrust eval-action:**
- Both run the same cases through the same agent — duplicate Bedrock calls, duplicate latency
- Braintrust eval-action provides everything Strands pytest provides (pass/fail gate) plus experiment comparison and PR comments
- The Strands pytest step is strictly dominated by Braintrust eval-action in CI

---

## EDD Development Workflow

```
1. Write new EvalCase in cases.py        ← define behavioral contract
2. Run: uv run pytest evals/ -m agent    ← fails (expected)
3. Update agent/tools/prompt/guardrail   ← implement behavior
4. Run evals again                       ← passes locally
5. Push PR                               ← eval-action posts score diff
6. Merge                                 ← new baseline recorded in Braintrust
```

This is the TDD red-green-refactor loop applied to agent behavior.

---

## Configuration

**`backend/pyproject.toml`** — testpaths updated:
```toml
[tool.pytest.ini_options]
testpaths = ["tests", "evals"]
```

**`backend/.env.example`** — local credentials template:
```
BRAINTRUST_API_KEY=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=us-east-1
SST_RESOURCE_Bookings={"name":"eval-stub"}
SST_RESOURCE_RestaurantKB={"id":"eval-stub"}
SST_RESOURCE_AgentSessions={"name":"eval-sessions"}
```

---

## Key Architectural Decisions

| Decision | Rationale |
|---|---|
| `cases.py` has zero framework imports | Data layer must be stable; coupling it to `strands_evals` or `braintrust` means editing it when framework APIs change |
| No converter functions | Each conversion is a one-liner called exactly once — named functions would be premature abstraction |
| Consolidate under `evals/` not `tests/` | Agent evals test model behavior, not code behavior; mixing them in `tests/` conflates two different concepts |
| `braintrust/` + `strands/` subdirs | Makes the credential requirement boundary explicit at the filesystem level |
| Remove Strands pytest from CI | Braintrust eval-action strictly dominates it in CI (same gate + richer signals); keep Strands for local iteration only |
| OTel evaluators deferred to v2 | `FaithfulnessEvaluator` has low signal until real KB responses are available; `ToolSelectionEvaluator` is redundant with deterministic trajectory scorer |
