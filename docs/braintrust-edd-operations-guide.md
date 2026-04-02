# Braintrust EDD Operations Guide

This guide documents the current Evaluation Driven Development workflow for the
Restaurant Booking Agent. It is meant to be a practical setup and operations
reference: how prompts are managed, how datasets are seeded, how evals run
locally, how GitHub Actions is wired, and how to debug the failures we already
hit on this branch.

## Purpose

The current eval stack is built around one Braintrust project:

- Project: `Restaurant Booking Agent`
- Prompt slug: `restaurant-booking-agent-system`
- Datasets:
  - `restaurant-agent-output-quality`
  - `restaurant-agent-trajectory`

The goal is to keep prompt management, dataset management, local eval runs, and
CI eval runs all pointing at the same Braintrust project and the same repo-owned
test cases.

## Repo Components

### Prompt management

The checked-in system prompt still lives in application code:

- `backend/app/agent/prompts.py`

The managed Braintrust prompt definition lives here:

- `backend/braintrust/prompts/restaurant_booking_agent.py`

The runtime prompt loader lives here:

- `backend/app/agent/prompt_loader.py`

Current behavior:

- if no Braintrust prompt version or environment is configured, the app uses the
  local checked-in `SYSTEM_PROMPT`
- if `BRAINTRUST_PROMPT_VERSION` or `BRAINTRUST_PROMPT_ENVIRONMENT` is set, the
  app loads the managed prompt from Braintrust

### Eval cases and datasets

Repo-authored eval cases live in:

- `backend/evals/cases.py`

Managed Braintrust dataset seeding lives in:

- `backend/scripts/create_braintrust_dataset.py`

Current datasets:

- output quality dataset: `restaurant-agent-output-quality`
- trajectory dataset: `restaurant-agent-trajectory`

### Braintrust eval runners

The two Braintrust eval entrypoints are:

- `backend/evals/braintrust/eval_output_quality.py`
- `backend/evals/braintrust/eval_trajectory.py`

They both:

- initialize the dataset from Braintrust
- construct a deterministic eval agent
- stub external dependencies
- upload experiments into the single Braintrust project

### CI workflows

GitHub Actions files:

- `.github/workflows/ci.yml`
- `.github/workflows/evals.yml`

Current responsibilities:

- `ci.yml`
  - backend lint
  - backend unit tests
  - SST diff on pull requests
- `evals.yml`
  - installs `uv`
  - syncs backend dependencies
  - runs Braintrust evals using `braintrustdata/eval-action@v1`

## Local Setup

### 1. Install dependencies

From the repo root:

```bash
pnpm install
cd backend && uv sync --frozen --group dev
```

### 2. Create backend env file

Copy the example file:

```bash
cd backend
cp .env.example .env
```

Fill in at least:

- `BRAINTRUST_API_KEY`
- AWS values if you want to run evals or other AWS-backed flows locally

### 3. Verify AWS identity locally

These commands help confirm which AWS profile is active and which credentials
you are using:

```bash
echo "${AWS_PROFILE:-default}"
aws configure get aws_access_key_id --profile "${AWS_PROFILE:-default}"
aws configure get aws_secret_access_key --profile "${AWS_PROFILE:-default}"
aws configure get region --profile "${AWS_PROFILE:-default}"
aws sts get-caller-identity --profile "${AWS_PROFILE:-default}"
```

## Prompt Management Workflow

Push the managed system prompt to Braintrust:

```bash
pnpm braintrust:push:prompts
```

Equivalent backend command:

```bash
cd backend
uv run braintrust push --env-file .env braintrust/prompts/restaurant_booking_agent.py
```

Notes:

- the prompt is created inside the `Restaurant Booking Agent` Braintrust project
- the stable slug is `restaurant-booking-agent-system`
- prompt loading in the app is opt-in via environment variables, so local app
  behavior remains stable unless managed prompt loading is explicitly enabled

Examples:

```bash
export BRAINTRUST_PROMPT_ENVIRONMENT=development
```

or

```bash
export BRAINTRUST_PROMPT_VERSION=<version-id>
```

## Dataset Seeding Workflow

Seed or refresh the managed Braintrust datasets from the repo-authored eval
cases:

```bash
pnpm eval:braintrust:seed
```

Equivalent backend command:

```bash
cd backend
uv run python scripts/create_braintrust_dataset.py
```

This script:

- loads `backend/.env`
- initializes the Braintrust datasets under `Restaurant Booking Agent`
- upserts records using the stable `EvalCase.id`

That means re-running it updates existing records instead of duplicating them.

## Running Evals Locally

### Output quality eval

```bash
pnpm eval:braintrust:quality
```

Equivalent:

```bash
cd backend
uv run braintrust eval --env-file .env evals/braintrust/eval_output_quality.py
```

Local iteration without sending logs:

```bash
cd backend
uv run braintrust eval --env-file .env --no-send-logs evals/braintrust/eval_output_quality.py
```

### Trajectory eval

```bash
pnpm eval:braintrust:trajectory
```

Equivalent:

```bash
cd backend
uv run braintrust eval --env-file .env evals/braintrust/eval_trajectory.py
```

Local iteration without sending logs:

```bash
cd backend
uv run braintrust eval --env-file .env --no-send-logs evals/braintrust/eval_trajectory.py
```

## Local Verification Commands

These are the commands that proved useful while debugging and stabilizing this
branch.

### Backend lint

```bash
cd backend
uv run ruff check --output-format=github .
uv run ruff format --check .
uv run pylint app/ --rcfile=pyproject.toml
```

### Unit tests

```bash
cd backend
uv run pytest tests/unit/ -q
```

### Broader backend tests

```bash
pnpm test:backend:fast
pnpm test:backend
```

### Typecheck

```bash
pnpm typecheck
```

## GitHub Actions Setup

### Evals workflow

The Braintrust eval workflow depends on:

- `astral-sh/setup-uv@v7`
- `uv sync --frozen --group dev`
- `braintrustdata/eval-action@v1`

Important details:

- `braintrustdata/eval-action` does not provision your Python environment for
  you, so `uv` must be installed before the action runs
- the workflow uses `paths: evals/braintrust`, not a multiline file list
- the workflow passes minimal SST resource stubs so backend config imports can
  succeed during eval runs without a live deployed stack

### CI workflow

The main CI workflow currently does three things:

1. backend lint
2. unit tests
3. SST diff on pull requests

The SST diff job needs AWS credentials in GitHub Actions because `sst diff`
must talk to AWS.

## Setting GitHub Secrets with `gh`

You can set the required secrets programmatically from your terminal using the
GitHub CLI.

### Braintrust secret

```bash
gh secret set BRAINTRUST_API_KEY --body "YOUR_BRAINTRUST_API_KEY"
```

### AWS secrets

If your local AWS CLI is configured with static credentials:

```bash
gh secret set AWS_ACCESS_KEY_ID --body "$(aws configure get aws_access_key_id --profile "${AWS_PROFILE:-default}")"
gh secret set AWS_SECRET_ACCESS_KEY --body "$(aws configure get aws_secret_access_key --profile "${AWS_PROFILE:-default}")"
```

Optional region secret:

```bash
gh secret set AWS_REGION --body "$(aws configure get region --profile "${AWS_PROFILE:-default}")"
```

### Verify secrets exist

```bash
gh secret list
```

If you need to target the repo explicitly:

```bash
gh secret set AWS_ACCESS_KEY_ID --repo Facundo-Martin/restaurant-booking-agent --body "$(aws configure get aws_access_key_id --profile "${AWS_PROFILE:-default}")"
```

## Common Failures and Fixes

### `uv: not found` in evals

Cause:

- the workflow tried to run Braintrust without installing `uv`

Fix:

- install `uv` with `astral-sh/setup-uv`
- run `uv sync --frozen --group dev` before the Braintrust action

### `braintrust: not found`

Cause:

- dependencies were not installed before `braintrustdata/eval-action`

Fix:

- provision the Python environment before the action runs

### `Invalid API key : [401] No authentication token`

Cause:

- `BRAINTRUST_API_KEY` was missing or empty in GitHub Actions

Fix:

```bash
gh secret set BRAINTRUST_API_KEY --body "YOUR_BRAINTRUST_API_KEY"
gh secret list
```

### `AWS credentials are not configured` in `sst diff`

Cause:

- GitHub Actions did not have valid AWS credentials

Fix:

```bash
gh secret set AWS_ACCESS_KEY_ID --body "$(aws configure get aws_access_key_id --profile "${AWS_PROFILE:-default}")"
gh secret set AWS_SECRET_ACCESS_KEY --body "$(aws configure get aws_secret_access_key --profile "${AWS_PROFILE:-default}")"
gh secret list
```

### Ruff vs Pylint import-order conflict

Cause:

- Ruff and Pylint disagreed about import classification and both tried to own
  import ordering

Fix:

- let Ruff own import ordering
- disable Pylint `C0411` (`wrong-import-order`) in `backend/pyproject.toml`

### Unit tests failing with `NoRegionError`

Cause:

- `backend/app/repositories/bookings.py` initialized DynamoDB at import time
- unit test collection imported the repository before Moto and region setup

Fix:

- switch to lazy table initialization in the repository
- add a regression test proving module import does not call `boto3.resource()`

## Recommended Operating Model

For the current system, the cleanest workflow is:

1. update prompt or eval cases in the repo
2. push the managed Braintrust prompt if needed
3. reseed datasets if cases changed
4. run local lint and unit tests
5. run local Braintrust evals
6. push the branch and let GitHub Actions run CI and evals

In practice, that usually looks like:

```bash
pnpm braintrust:push:prompts
pnpm eval:braintrust:seed
cd backend && uv run ruff check --output-format=github .
cd backend && uv run pylint app/ --rcfile=pyproject.toml
cd backend && uv run pytest tests/unit/ -q
pnpm eval:braintrust:trajectory
pnpm eval:braintrust:quality
```

## Next-Level Hardening

The current setup is working, but there is still a bigger EDD hardening pass to
do later. That roadmap lives here:

- `docs/superpowers/plans/2026-04-02-edd-consolidation-hardening.md`

That plan covers the next step up in rigor:

- prompt provenance
- dataset version pinning
- fail-closed eval preflight checks
- stronger experiment metadata
- more robust EDD hygiene around reproducibility
