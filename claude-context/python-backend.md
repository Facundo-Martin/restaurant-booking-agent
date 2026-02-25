# Python Backend — Tooling Reference

This document captures the modern Python toolchain chosen for `backend/` and explains why each tool was included or skipped. Sources: the Astral ecosystem recommendations (mameli.dev, copier-astral template), filtered for what actually makes sense for a **FastAPI + Lambda + Strands Agents** service — not a data science project.

---

## The Astral Ecosystem

[Astral](https://astral.sh) is the company behind `uv` and `ruff`. Their tools share a philosophy: take something the Python ecosystem does slowly or inconsistently (package management, linting, formatting, type checking) and rewrite it in Rust to be 10–100× faster with better defaults.

The tools in this project that come from Astral: `uv`, `ruff`, and `ty` (type checker, currently beta). We also use `prek` — not an Astral product, but a Rust-based drop-in replacement for `pre-commit` built by a contributor closely tied to the Astral ecosystem, already adopted by Ruff, CPython, and FastAPI themselves.

---

## Chosen Toolchain

### `uv` — package manager + virtual environment

Replaces: `pip`, `pip-tools`, `virtualenv`, `pyenv`

`uv` is the foundation. It manages the virtual environment, resolves and locks dependencies, and pins the Python version. Every `uv` command is a drop-in for a slower equivalent:

```bash
uv add fastapi          # replaces: pip install fastapi
uv add --dev pytest     # replaces: pip install --dev pytest
uv lock                 # replaces: pip-compile
uv sync                 # replaces: pip install -r requirements.txt
uv run pytest           # runs pytest inside the venv without activating it
```

The lockfile (`uv.lock`) is the Python equivalent of `pnpm-lock.yaml` — it pins every transitive dependency to an exact version. Commit it.

SST's Python bundler requires a `pyproject.toml` at `backend/` and calls `uv` internally to build the Lambda deployment package. This is the only reason we need `uv` specifically (not `poetry` or plain `pip`) — SST hard-depends on it.

---

### `ruff` — linter + formatter

Replaces: `flake8`, `black`, `isort`, `pylint` (partially)

`ruff` does two things in one tool and does them extremely fast:

- **Formatting**: enforces consistent code style (equivalent to `black`)
- **Linting**: catches bugs, style violations, unused imports, etc. (equivalent to `flake8` + `isort` + many plugins)

Without `ruff`, you'd configure three separate tools with three config sections that can contradict each other. With `ruff`, it's one `[tool.ruff]` section in `pyproject.toml`.

Configuration lives in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 88
target-version = "py311"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes (unused imports, undefined names)
    "I",   # isort (import ordering)
    "B",   # flake8-bugbear (common bugs and design issues)
    "UP",  # pyupgrade (modernise syntax for the target Python version)
]
ignore = [
    "E501", # line too long — handled by formatter
]

[tool.ruff.lint.isort]
known-first-party = ["app"]
```

Daily usage:
```bash
uv run ruff format .       # format all files
uv run ruff check .        # lint
uv run ruff check . --fix  # lint + auto-fix what can be fixed
```

---

### `ty` — type checker

Replaces: `mypy`, `pyright`

`ty` is Astral's type checker — same philosophy as `ruff` and `uv`: rewrite something slow in Rust, get 10–100× faster, ship better defaults. Currently in beta (`0.0.x`) but functional enough for day-to-day use.

The bet here is deliberate: `ty` is highly swappable. If it turns out to be too rough for a few months, switching back to `pyright` is a one-line change in `pyproject.toml` and a `uv add` command. The migration cost is nothing like switching a cloud provider or a database. Supporting the Astral ecosystem early is worth that minor risk.

Usage via `uvx` (no install needed):
```bash
uvx ty check app/
```

Or as a dev dependency, run through uv:
```bash
uv run ty check app/
```

> **`ty` configuration** is still stabilising — check `docs.astral.sh/ty` for the latest `[tool.ty]` options as they mature. For now, running it with defaults is fine.

---

### `pytest` — testing

The standard. Three plugins are added on top:

| Plugin | Purpose |
|---|---|
| `pytest-asyncio` | Run async test functions — needed for FastAPI's async route handlers |
| `moto` | Mock AWS services (DynamoDB, S3, etc.) so tests never hit real AWS |
| `httpx` | FastAPI's `TestClient` uses `httpx` under the hood for HTTP-level tests |

Configuration in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"   # all async test functions run under asyncio automatically
```

Usage:
```bash
uv run pytest              # run all tests
uv run pytest tests/unit   # run only unit tests
uv run pytest -v -s        # verbose with stdout (useful when debugging)
```

---

### `prek` — git hooks

Replaces: `pre-commit`

`prek` is a Rust-based reimplementation of `pre-commit` by `j178` — a contributor closely tied to the Astral ecosystem. It is a single binary with no Python or runtime dependency, significantly faster than `pre-commit`, and uses the **exact same `.pre-commit-config.yaml` format**. The switch cost from `pre-commit` to `prek` is zero: same config file, same hooks, same ruff integration. It is already used by Ruff, CPython, FastAPI, and Apache Airflow.

The `.pre-commit-config.yaml` lives at the repo root (not inside `backend/`) and is identical regardless of whether you use `prek` or `pre-commit`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff          # lint + auto-fix
        args: [--fix]
      - id: ruff-format   # format
```

Setup (one-time per developer):
```bash
# Install prek as a standalone binary
curl -fsSL https://prek.j178.dev/install.sh | sh
# or: brew install j178/tap/prek

prek install   # installs the hook into .git/hooks/pre-commit
```

After that, every `git commit` runs ruff automatically. Commits fail if unfixable lint errors exist.

---

## Tools Evaluated and Skipped

| Tool | Reason skipped |
|---|---|
| `commitizen` | We handle conventional commits manually; adds a CLI wrapper we don't need |
| `git-cliff` | Changelog generation — useful later if we want automated release notes; skip for now |
| `semgrep` | Security SAST scanning — worth adding before production; overkill for POC |
| `gitleaks` | Secret scanning — worthwhile in CI eventually; skip for now |
| `Docker` | Lambda handles the runtime environment; no container needed for this deployment target |
| `MkDocs` | Documentation site — not needed for a POC |
| `Marimo` / `Polars` / `DuckDB` | Data science tools; irrelevant for a web API backend |
| `hatch` | Build system / test matrix runner — uv covers what we need |
| `Typer` | CLI framework — we're building an HTTP API, not a CLI tool |

---

## Final `pyproject.toml`

```toml
[project]
name = "restaurant-booking-agent-backend"
version = "0.1.0"
description = "FastAPI + Strands Agents backend for the restaurant booking assistant"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "mangum>=0.19.0",
    "strands-agents>=0.1.0",
    "strands-agents-tools>=0.1.0",
    "boto3>=1.34.0",
    "sst>=3.0.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",       # required by FastAPI TestClient
    "moto[dynamodb]>=5.0.0",
    "ty>=0.0.1",
    "ruff>=0.9.0",
]

[tool.ruff]
line-length = 88
target-version = "py311"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "UP"]
ignore = ["E501"]

[tool.ruff.lint.isort]
known-first-party = ["app"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

> **`[dependency-groups]` vs `[project.optional-dependencies]`**: `dependency-groups` is the newer uv-native way to declare dev dependencies (PEP 735). `uv sync --group dev` installs them; `uv sync` (no flag) skips them — which is what SST does when bundling for Lambda.

---

## Development Workflow

```bash
# Install everything including dev dependencies
uv sync --group dev

# Run the app locally (no Lambda needed)
uv run uvicorn app.main:app --reload

# Format + lint
uv run ruff format .
uv run ruff check . --fix

# Type check
uvx ty check app/

# Run tests
uv run pytest

# Run a single test file
uv run pytest tests/unit/tools/test_bookings.py -v
```

---

## What SST Does with This

When `sst deploy` runs:

1. SST finds `backend/pyproject.toml` via the handler path prefix (`"backend/app/handler_chat.handler"`)
2. It calls `uv sync` (without `--group dev`) to install only production dependencies into a temporary venv
3. It zips the venv site-packages + `app/` source code into a Lambda deployment package
4. It uploads the zip and updates the Lambda function

You never touch `pip`, `zip`, or the Lambda console. `uv` + SST handle the entire packaging pipeline.
