# EDD Consolidation and Hardening Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the current Braintrust + Strands evaluation setup from "working" to "robust, reproducible, and CI-friendly" by hardening experiment provenance, dataset/prompt versioning, eval preflight checks, scorer discipline, and automated verification.

**Architecture:** Treat a single evaluation run as a versioned artifact tuple:
- code revision (`git SHA`)
- dataset snapshot (`dataset name + dataset version`)
- prompt snapshot (`prompt slug + prompt version or environment-resolved version`)
- model config (`model id + generation parameters`)
- scorer config (`judge model id + rubric version`)

Every Braintrust experiment should record that tuple explicitly and fail closed when any member is missing or ambiguous.

**Why this plan exists:**
- Current Braintrust evals read the latest dataset version at runtime, which makes repeated runs of the same code potentially non-reproducible.
- Current prompt loading supports Braintrust-managed prompts, but experiment metadata does not record which prompt version was actually used.
- Dataset seeding and eval execution are decoupled, but the eval runners do not assert freshness or non-emptiness before starting.
- The output-quality judge currently treats `expected` prose as a fact source, which can mask hallucinations instead of detecting them.
- The current package-script workflow works, but it is still easy to run the "right command" against the wrong dataset or prompt state.

**Primary sources:**
- Braintrust Python SDK reference: https://www.braintrust.dev/docs/reference/sdks/python
- Braintrust prompts guide: https://www.braintrust.dev/docs/guides/functions/prompts
- Braintrust prompt versioning article: https://www.braintrust.dev/articles/what-is-prompt-versioning
- Braintrust evaluating agents guide: https://www.braintrust.dev/docs/best-practices/agents
- Braintrust evaluate systematically guide: https://www.braintrust.dev/docs/evaluate
- Braintrust agent evaluation article: https://www.braintrust.dev/articles/agent-evaluation

---

## File Map

| File | Change |
|---|---|
| `backend/evals/braintrust/config.py` | Expand from naming constants into a typed source of truth for project, dataset, prompt, and experiment metadata |
| `backend/evals/braintrust/manifest.py` | **New** — typed provenance model for dataset/prompt/model/scorer versions |
| `backend/evals/braintrust/datasets.py` | **New** — dataset loading, version pinning, emptiness checks, and authored-case parity checks |
| `backend/evals/braintrust/prompt_versions.py` | **New** — resolve prompt version metadata and normalize version/environment selection |
| `backend/evals/braintrust/common.py` | **New** — shared helpers for eval metadata, experiment naming, and model config |
| `backend/evals/braintrust/eval_output_quality.py` | Refactor to use pinned dataset + prompt provenance + shared preflight |
| `backend/evals/braintrust/eval_trajectory.py` | Refactor to use pinned dataset + prompt provenance + shared preflight |
| `backend/evals/cases.py` | Add optional rubric/provenance metadata and stricter typing for case categories |
| `backend/evals/scorers/output_quality_scorer.py` | Remove `expected` prose as a factual source; version the rubric explicitly |
| `backend/evals/scorers/trajectory_scorer.py` | Add explicit scorer version metadata and stricter result schema |
| `backend/evals/workflows/` | **New** — multi-turn workflow fixtures for cancellation and rescheduling |
| `backend/evals/braintrust/eval_cancellation_flow.py` | **New** — multi-turn authorization-aware cancellation eval |
| `backend/evals/scorers/workflow_scorer.py` | **New** — stepwise invariants for confirmation, ownership, and destructive tools |
| `backend/app/agent/prompt_loader.py` | Return structured prompt metadata, not just prompt text; cache loaded prompts |
| `backend/app/api/routes/chat.py` | Emit prompt provenance in traces/logs for runtime observability |
| `backend/braintrust/prompts/restaurant_booking_agent.py` | Add prompt metadata/version labels and comments about deployment workflow |
| `backend/scripts/create_braintrust_dataset.py` | Add dataset version output, case-count verification, and optional fail-on-drift mode |
| `backend/scripts/verify_eval_fixtures.py` | **New** — local preflight script that validates dataset/prompt state before eval execution |
| `backend/tests/unit/agent/test_prompt_loader.py` | Expand to cover caching, version metadata, and failure behavior |
| `backend/tests/unit/evals/test_braintrust_config.py` | Replace with richer config/manifest tests |
| `backend/tests/unit/evals/test_datasets.py` | **New** — dataset preflight and parity tests |
| `backend/tests/unit/evals/test_manifest.py` | **New** — provenance serialization tests |
| `backend/tests/unit/evals/test_output_quality_scorer.py` | **New** — judge prompt contract tests |
| `backend/tests/unit/evals/test_workflow_scorer.py` | **New** — multi-turn workflow scorer tests |
| `backend/tests/integration/test_agent.py` | Expand with authorization-aware cancellation/rescheduling regression tests |
| `backend/app/repositories/bookings.py` | Evolve read/delete/update operations to enforce booking ownership |
| `backend/app/tools/bookings.py` | Return ownership-safe results; add reschedule tool when supported |
| `package.json` | Add explicit preflight and CI eval commands |
| `.github/workflows/` | **Potential new files** — CI split between fast checks and eval gating |

---

## Target State

When this plan is complete:

1. A Braintrust experiment cannot start unless:
   - the dataset exists
   - the dataset is non-empty
   - the dataset version is explicitly recorded
   - the authored case count matches the managed dataset snapshot or the run aborts

2. A Braintrust experiment always records:
   - `project_name`
   - `dataset_name`
   - `dataset_version`
   - `prompt_slug`
   - `prompt_version`
   - `prompt_environment` if applicable
   - `agent_model_id`
   - `judge_model_id` where relevant
   - `scorer_version`
   - `commit`

3. The output-quality scorer judges behavior against:
   - user input
   - known tool outputs
   - explicit policy constraints

   It does **not** treat the freeform `expected` narrative as a second factual database.

4. The runtime prompt loader and eval prompt loader share one implementation that:
   - resolves version vs environment deterministically
   - caches loaded prompt definitions
   - exposes both prompt text and prompt provenance

5. Package scripts encode the intended workflow:
   - preflight
   - seed
   - push prompts
   - run evals

6. Destructive booking flows are authorization-safe:
   - booking lookup, cancellation, and future rescheduling operate only on bookings
     owned by the authenticated user
   - workflows do not reveal whether another user's booking exists
   - destructive tools only fire after both ownership validation and explicit user
     confirmation

7. The eval architecture covers both:
   - single-turn policy checks (fast regression guards)
   - multi-turn workflow checks (end-to-end confirmation and authorization flows)

---

## Task 1: Introduce Typed Eval Provenance

**Files:**
- Create: `backend/evals/braintrust/manifest.py`
- Modify: `backend/evals/braintrust/config.py`
- Test: `backend/tests/unit/evals/test_manifest.py`

- [ ] **Step 1: Create a provenance model**

Add `backend/evals/braintrust/manifest.py`:

```python
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EvalProvenance:
    project_name: str
    dataset_name: str
    dataset_version: str | int
    prompt_slug: str
    prompt_version: str | int | None
    prompt_environment: str | None
    agent_model_id: str
    judge_model_id: str | None
    scorer_version: str
    commit: str

    def to_metadata(self) -> dict[str, object]:
        return asdict(self)
```

- [ ] **Step 2: Refactor `config.py` into constants + version labels**

Add explicit constants for:
- agent model id
- judge model id
- scorer version strings
- default dataset version mode (`latest` only for local dev, never for CI)

Keep `config.py` dependency-light.

- [ ] **Step 3: Add unit tests**

Create tests that verify:
- serialization shape is stable
- required fields are never omitted
- scorer versions and model ids are not empty strings

- [ ] **Step 4: Commit**

```bash
git add backend/evals/braintrust/manifest.py \
        backend/evals/braintrust/config.py \
        backend/tests/unit/evals/test_manifest.py
git commit -m "feat(evals): add typed experiment provenance model"
```

**Source notes:**
- Braintrust datasets and prompts are versionable objects in the Python SDK and prompts guide. This task formalizes those concepts inside the repo so experiments can carry full provenance rather than ad hoc metadata.
- Sources:
  - https://www.braintrust.dev/docs/reference/sdks/python
  - https://www.braintrust.dev/docs/guides/functions/prompts

---

## Task 2: Pin Dataset Versions and Fail Closed on Fixture Drift

**Files:**
- Create: `backend/evals/braintrust/datasets.py`
- Modify: `backend/evals/braintrust/eval_output_quality.py`
- Modify: `backend/evals/braintrust/eval_trajectory.py`
- Modify: `backend/scripts/create_braintrust_dataset.py`
- Test: `backend/tests/unit/evals/test_datasets.py`

- [ ] **Step 1: Create dataset loader helpers**

Add `backend/evals/braintrust/datasets.py`:

```python
import dataclasses

import braintrust


def load_dataset(project: str, name: str, version: str | int | None):
    dataset = braintrust.init_dataset(project=project, name=name, version=version)
    rows = list(dataset)
    if not rows:
        raise RuntimeError(f"Braintrust dataset '{name}' is empty; seed it before running evals")
    return dataset, rows


def assert_case_count_matches(rows: list[object], authored_cases: list[object], dataset_name: str) -> None:
    if len(rows) != len(authored_cases):
        raise RuntimeError(
            f"Dataset '{dataset_name}' has {len(rows)} rows but evals/cases.py defines {len(authored_cases)} cases"
        )
```

- [ ] **Step 2: Thread dataset version through the eval runners**

Add env-driven version selection:
- `BRAINTRUST_OUTPUT_QUALITY_DATASET_VERSION`
- `BRAINTRUST_TRAJECTORY_DATASET_VERSION`

In CI, require them to be set.
For local runs, allow `None` but record that the run used "latest".

- [ ] **Step 3: Make eval runners abort if datasets are empty or mismatched**

In each eval file:
- load the dataset through `datasets.py`
- list the rows once
- compare row count to authored cases in `evals/cases.py`
- abort early if counts diverge

This should happen before `Eval(...)` is invoked.

- [ ] **Step 4: Improve the seed script**

Update `backend/scripts/create_braintrust_dataset.py` to print:
- dataset name
- seeded row count
- resulting dataset version if Braintrust exposes it

Also add a `--fail-on-count-mismatch` mode if useful.

- [ ] **Step 5: Add tests**

Create tests for:
- empty dataset rejection
- authored-case parity failure
- explicit version forwarding into `braintrust.init_dataset(...)`

- [ ] **Step 6: Commit**

```bash
git add backend/evals/braintrust/datasets.py \
        backend/evals/braintrust/eval_output_quality.py \
        backend/evals/braintrust/eval_trajectory.py \
        backend/scripts/create_braintrust_dataset.py \
        backend/tests/unit/evals/test_datasets.py
git commit -m "feat(evals): pin dataset loading and fail on fixture drift"
```

**Source notes:**
- Braintrust's Python SDK exposes dataset versions through `init_dataset(..., version=...)`. Not pinning the version means runs consume the latest snapshot implicitly.
- Source: https://www.braintrust.dev/docs/reference/sdks/python

---

## Task 3: Make Prompt Versioning Operational, Not Just Available

**Files:**
- Modify: `backend/app/agent/prompt_loader.py`
- Create: `backend/evals/braintrust/prompt_versions.py`
- Modify: `backend/evals/braintrust/eval_output_quality.py`
- Modify: `backend/evals/braintrust/eval_trajectory.py`
- Test: `backend/tests/unit/agent/test_prompt_loader.py`

- [ ] **Step 1: Return structured prompt metadata**

Refactor `load_system_prompt()` into:

```python
@dataclass(frozen=True)
class LoadedPrompt:
    text: str
    slug: str
    version: str | int | None
    environment: str | None
    source: str  # "local" | "braintrust"
```

Then rename the loader to something like `load_system_prompt_bundle()`.

- [ ] **Step 2: Cache prompt resolution**

Wrap the loader with `functools.lru_cache(maxsize=8)` keyed by `(version, environment)` so:
- runtime requests do not fetch Braintrust every time
- eval runs use one prompt snapshot per process

- [ ] **Step 3: Resolve and record prompt provenance**

Add a helper in `prompt_versions.py` that:
- reads env vars
- enforces `version` precedence over `environment`
- rejects impossible combinations if needed

Use the returned metadata to populate `EvalProvenance`.

- [ ] **Step 4: Update eval runners to log the loaded prompt version**

Each eval runner should:
- resolve the prompt bundle once at module load or preflight time
- pass `bundle.text` to the agent
- include `bundle.slug`, `bundle.version`, and `bundle.environment` in experiment metadata

- [ ] **Step 5: Expand tests**

Add unit coverage for:
- cache behavior
- structured return type
- local fallback metadata
- environment-only resolution
- explicit version override

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/prompt_loader.py \
        backend/evals/braintrust/prompt_versions.py \
        backend/evals/braintrust/eval_output_quality.py \
        backend/evals/braintrust/eval_trajectory.py \
        backend/tests/unit/agent/test_prompt_loader.py
git commit -m "feat(prompts): capture prompt provenance and cache managed loads"
```

**Source notes:**
- Braintrust prompt slugs are stable identifiers across prompt updates, and prompt versions are a first-class concept. The architecture should preserve that provenance in experiment metadata instead of collapsing everything to raw prompt text.
- Sources:
  - https://www.braintrust.dev/docs/guides/functions/prompts
  - https://www.braintrust.dev/articles/what-is-prompt-versioning

---

## Task 4: Tighten the Output-Quality Judge Contract

**Files:**
- Modify: `backend/evals/scorers/output_quality_scorer.py`
- Create: `backend/tests/unit/evals/test_output_quality_scorer.py`
- Modify: `backend/evals/cases.py`

- [ ] **Step 1: Separate policy expectations from factual expectations**

Refactor `EvalCase.expected` for output-quality rows into clearer fields:

```python
@dataclass(frozen=True)
class OutputQualityExpectation:
    behavioral_requirements: str
    allowed_facts: dict[str, object] = field(default_factory=dict)
```

If a full type migration is too disruptive, keep `expected` as-is for now but add `metadata["allowed_facts"]` and teach the scorer to prefer that field.

- [ ] **Step 2: Remove "expected prose is factual truth" from the rubric**

In the judge prompt, replace:
- "List every fact in expected behavior"

with:
- "Use only the user input and explicit tool context as authoritative facts unless `allowed_facts` is provided."

That keeps the judge from treating sloppy case prose as a second KB.

- [ ] **Step 3: Version the scorer**

Add:

```python
SCORER_VERSION = "output-quality-v2"
```

and return it in scorer metadata. This makes score changes auditable when the rubric evolves.

- [ ] **Step 4: Add scorer contract tests**

Create unit tests that assert:
- the scorer returns the expected metadata keys
- the prompt template contains no "expected behavior facts are canonical" language
- parsing falls back conservatively to `N`

- [ ] **Step 5: Commit**

```bash
git add backend/evals/scorers/output_quality_scorer.py \
        backend/evals/cases.py \
        backend/tests/unit/evals/test_output_quality_scorer.py
git commit -m "refactor(evals): harden output-quality judge against fact leakage"
```

**Source notes:**
- This is a repo-architecture refinement rather than a Braintrust API requirement, but it follows the general EDD principle that scorers should measure the model against stable acceptance criteria, not against mutable freeform prose.

---

## Task 5: Standardize Eval Runner Construction

**Files:**
- Create: `backend/evals/braintrust/common.py`
- Modify: `backend/evals/braintrust/eval_output_quality.py`
- Modify: `backend/evals/braintrust/eval_trajectory.py`
- Modify: `backend/app/agent/core.py`

- [ ] **Step 1: Extract shared runner settings**

Move the duplicated parts into `common.py`:
- `_AGENT_MODEL` construction
- fake restaurant payload
- fake booking payload
- `retrieve` stub wiring
- shared metadata assembly

- [ ] **Step 2: Keep eval-specific logic thin**

After extraction, each eval file should only define:
- the task function shape
- the scorer list
- the dataset name/version inputs
- the experiment name

- [ ] **Step 3: Keep runtime and eval models intentionally distinct**

Do **not** silently reuse runtime `model` from `app.agent.core`. Keep the eval model declared in one shared eval-only module so:
- runtime changes do not accidentally mutate eval cost/latency behavior
- eval model changes are explicit architectural decisions

- [ ] **Step 4: Commit**

```bash
git add backend/evals/braintrust/common.py \
        backend/evals/braintrust/eval_output_quality.py \
        backend/evals/braintrust/eval_trajectory.py \
        backend/app/agent/core.py
git commit -m "refactor(evals): extract shared braintrust runner infrastructure"
```

---

## Task 6: Add Preflight and CI-Safe Commands

**Files:**
- Create: `backend/scripts/verify_eval_fixtures.py`
- Modify: `package.json`
- Potentially create: `.github/workflows/evals.yml`

- [ ] **Step 1: Add a preflight verifier**

Create `backend/scripts/verify_eval_fixtures.py` that checks:
- required env vars exist
- prompt can be resolved
- datasets exist and are non-empty
- authored case counts match managed dataset counts

Exit non-zero on any failure.

- [ ] **Step 2: Encode the intended package workflow**

Add scripts:

```json
{
  "scripts": {
    "eval:braintrust:preflight": "cd backend && uv run python scripts/verify_eval_fixtures.py",
    "eval:braintrust:ci:quality": "pnpm eval:braintrust:preflight && pnpm eval:braintrust:quality",
    "eval:braintrust:ci:trajectory": "pnpm eval:braintrust:preflight && pnpm eval:braintrust:trajectory"
  }
}
```

- [ ] **Step 3: CI design**

If CI is in scope on the new branch, split jobs into:
- `backend-fast` — unit/integration minus agent tests
- `braintrust-preflight`
- `braintrust-trajectory`
- `braintrust-output-quality`

Do not run the expensive evals on every PR unless the team explicitly wants that cost profile.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/verify_eval_fixtures.py package.json .github/workflows/evals.yml
git commit -m "chore(evals): add preflight and CI-safe braintrust commands"
```

If the workflow file is not added in this branch, omit it from the commit.

**Source notes:**
- Braintrust supports persistent experiment history, but robust CI usage still depends on local repo discipline: fail early, surface provenance, and separate cheap checks from expensive model-backed evals.
- Sources:
  - https://www.braintrust.dev/docs/reference
  - https://www.braintrust.dev/docs/reference/sdks/python

---

## Task 7: Add Multi-Turn, Authorization-Aware Workflow Evals

**Why this task exists:**
- The current eval suite is strong on single-turn policy checks, but cancellation and
  rescheduling are actually workflow problems, not single-message problems.
- A realistic booking cancellation flow may need to:
  1. verify the booking exists
  2. verify the booking belongs to the authenticated user
  3. ask the user for confirmation
  4. only then perform the destructive action
- That behavior is hard to encode cleanly in the current single-turn trajectory cases.
- Braintrust's agent-evaluation guidance explicitly recommends evaluating both the
  complete end-to-end task flow and the intermediate steps, and notes that `hooks`
  metadata can capture intermediate tool calls for scorers.

**Files:**
- Create: `backend/evals/workflows/cancellation_cases.py`
- Create: `backend/evals/braintrust/eval_cancellation_flow.py`
- Create: `backend/evals/scorers/workflow_scorer.py`
- Create: `backend/tests/unit/evals/test_workflow_scorer.py`
- Modify: `backend/evals/cases.py`
- Modify: `backend/app/repositories/bookings.py`
- Modify: `backend/app/tools/bookings.py`
- Modify: `backend/tests/integration/test_agent.py`

- [ ] **Step 1: Define the product policy explicitly**

Before implementation, choose and document one cancellation policy:

1. `lookup_then_confirm` (recommended)
   - call `get_booking_details`
   - verify the booking belongs to the authenticated user
   - ask for yes/no confirmation
   - call `delete_booking` only after confirmation

2. `confirm_then_lookup`
   - ask for confirmation first
   - only then perform lookup + ownership verification + deletion

Recommendation: adopt `lookup_then_confirm` because it avoids asking the user to
confirm an action against a booking that may not exist or may not belong to them.

- [ ] **Step 2: Make booking operations ownership-aware at the repository/tool layer**

The authorization boundary must live in code, not just in prompts.

Target direction:

```python
def get_for_user(booking_id: str, user_id: str) -> Booking | None:
    booking = get(booking_id)
    if booking is None or booking.user_id != user_id:
        return None
    return booking


def delete_for_user(booking_id: str, user_id: str) -> bool:
    booking = get_for_user(booking_id, user_id)
    if booking is None:
        return False
    return delete(booking_id)
```

Then the tool layer should expose only ownership-safe outcomes. If a booking does
not belong to the caller, return the same not-found-style response used for a
nonexistent booking to avoid leaking cross-user existence.

- [ ] **Step 3: Introduce multi-turn workflow fixtures**

Create workflow-style fixtures that model full conversational state, not just a
single message. At minimum:

- `cancel-existing-booking-confirm-yes`
- `cancel-existing-booking-confirm-no`
- `cancel-missing-booking`
- `cancel-other-users-booking`
- `reschedule-existing-booking-confirm-yes`
- `reschedule-other-users-booking`

Suggested shape:

```python
@dataclass(frozen=True)
class WorkflowTurn:
    role: str
    content: str


@dataclass(frozen=True)
class WorkflowCase:
    id: str
    turns: list[WorkflowTurn]
    expected_tool_sequence: list[str]
    metadata: dict[str, object] = field(default_factory=dict)
```

Use these workflow fixtures alongside, not instead of, the current single-turn
cases. Single-turn checks remain useful as fast regression gates.

- [ ] **Step 4: Build a Braintrust workflow eval harness**

Create `backend/evals/braintrust/eval_cancellation_flow.py` that:
- replays the conversation turn-by-turn
- preserves agent state across turns
- captures intermediate tool calls and state transitions
- stores those tool calls in `hooks.metadata`

Illustrative shape:

```python
async def task(case: WorkflowCase, hooks):
    transcript = []
    tool_calls = []

    agent = make_eval_agent()

    for turn in case.turns:
        if turn.role != "user":
            continue
        response = await agent.invoke_async(turn.content)
        transcript.append({"role": "user", "content": turn.content})
        transcript.append({"role": "assistant", "content": str(response)})
        tool_calls.extend(extract_tool_calls(agent.messages))

    hooks.metadata["tool_calls"] = tool_calls
    hooks.metadata["transcript"] = transcript
    return {"output": transcript[-1]["content"], "tool_calls": tool_calls}
```

This follows Braintrust's recommendation to evaluate both the complete task flow
and the intermediate steps, with `hooks.metadata` carrying the intermediate
artifacts that scorers need.

- [ ] **Step 5: Add invariant-based workflow scorers**

Create `workflow_scorer.py` to enforce the actual business/security rules:

- `delete_booking` must never fire before explicit confirmation
- `delete_booking` must not fire on a `"no"` response
- `get_booking_details` may be required before destructive actions if policy is
  `lookup_then_confirm`
- destructive tools must not operate on bookings owned by a different user
- cross-user access attempts must not leak booking details

Illustrative invariant:

```python
def assert_delete_after_confirmation(tool_calls: list[str], transcript: list[dict]) -> None:
    delete_index = tool_calls.index("delete_booking")
    assert any(
        turn["role"] == "user" and turn["content"].lower() in {"yes", "yes, cancel it"}
        for turn in transcript[: delete_index + 1]
    )
```

The exact implementation can be more robust, but the key idea is that multi-turn
workflow scoring should encode invariants, not just exact strings.

- [ ] **Step 6: Split single-turn vs workflow eval responsibilities**

Refine `backend/evals/cases.py` so it clearly distinguishes:

- single-turn policy/routing checks
- multi-turn workflow checks

Do not overload one case type to do both jobs. In practice:
- keep trajectory/output-quality datasets for fast, simple checks
- create dedicated workflow evals for cancellation/rescheduling conversations

- [ ] **Step 7: Expand integration tests**

Add integration tests that reflect the same security posture:

- authenticated user can cancel their own booking after confirmation
- authenticated user cannot cancel another user's booking
- authenticated user cannot reschedule another user's booking
- missing booking IDs and cross-user booking IDs return the same safe response shape

- [ ] **Step 8: Commit**

```bash
git add backend/evals/workflows \
        backend/evals/braintrust/eval_cancellation_flow.py \
        backend/evals/scorers/workflow_scorer.py \
        backend/evals/cases.py \
        backend/app/repositories/bookings.py \
        backend/app/tools/bookings.py \
        backend/tests/unit/evals/test_workflow_scorer.py \
        backend/tests/integration/test_agent.py
git commit -m "feat(evals): add multi-turn authorization-aware booking workflow evals"
```

**Source notes:**
- Braintrust's agent-evaluation guidance recommends evaluating agents both
  end-to-end and at each step, and explicitly describes using `hooks.metadata`
  to surface intermediate tool calls for scorers.
- Braintrust's evaluation guides emphasize that datasets, task functions, and
  scorers should represent the real task flow you care about. Cancellation and
  rescheduling are destructive, multi-step workflows, so they merit dedicated
  workflow evals rather than being forced into a single-turn routing-only shape.
- Sources:
  - https://www.braintrust.dev/docs/best-practices/agents
  - https://www.braintrust.dev/docs/evaluate
  - https://www.braintrust.dev/articles/agent-evaluation

---

## Task 8: Verification and Acceptance Criteria

- [ ] **Step 1: Unit verification**

Run:

```bash
cd backend && uv run pytest tests/unit/evals tests/unit/agent/test_prompt_loader.py -q
```

Expected:
- all new provenance/prompt/dataset/scorer tests pass

- [ ] **Step 2: Fast backend verification**

Run:

```bash
pnpm test:backend:fast
```

Expected:
- backend tests still pass

- [ ] **Step 3: Preflight verification**

Run:

```bash
pnpm eval:braintrust:preflight
```

Expected:
- prompt provenance resolved
- datasets found and non-empty
- authored case counts match managed datasets

- [ ] **Step 4: Braintrust experiment verification**

Run:

```bash
pnpm eval:braintrust:trajectory
pnpm eval:braintrust:quality
```

Expected:
- both runs complete
- both runs record dataset + prompt provenance in metadata
- no "0 data rows found" warnings

- [ ] **Step 5: Manual UI verification**

In Braintrust UI, verify:
- both experiments live under `Restaurant Booking Agent`
- experiment metadata shows dataset version and prompt version
- prompt slug is stable across pushes
- comparisons can distinguish prompt changes from code changes

---

## Self-Review

**Spec coverage:**
- Reproducibility: covered by Tasks 1-3
- Eval robustness: covered by Tasks 2, 4, and 6
- Better architecture: covered by Tasks 1, 3, and 5
- EDD best practices: covered by provenance, preflight, scorer hardening, and CI workflow design

**Placeholder scan:**
- No TODO/TBD steps
- All new modules and commands are named explicitly
- Verification commands are concrete

**Type consistency:**
- `EvalProvenance` is the single metadata model
- `LoadedPrompt` is the single prompt-loading result model
- Dataset/prompt versioning terminology is consistent throughout

---

Plan complete and saved to `docs/superpowers/plans/2026-04-02-edd-consolidation-hardening.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
