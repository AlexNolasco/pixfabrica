# Pixfabrica task runner — requires `just` (https://just.systems)
# Works on Windows (Git Bash) and Linux identically.

set windows-shell := ["cmd.exe", "/c"]

default:
    @just --list

# ── Setup ─────────────────────────────────────────────────────────────────────

# Install all Python dependencies (creates .venv automatically)
install:
    uv sync --all-packages

# Install with dev dependencies
install-dev:
    uv sync --all-packages --group dev

# ── Tests ─────────────────────────────────────────────────────────────────────

test:
    uv run pytest

test-v:
    uv run pytest -v

test-cov:
    uv run pytest --cov --cov-report=term-missing

# ── Code quality ──────────────────────────────────────────────────────────────

lint:
    uv run ruff check .

fmt:
    uv run ruff format .

fmt-check:
    uv run ruff format --check .

typecheck:
    uv run pyright

# Enforce the stateless draw() contract — no cross-frame self.* mutations.
# See plugins/README.md and VisualClip docstring for the full contract.
check-stateless:
    uv run python scripts/check_stateless_draw.py

check-cli-no-web:
    uv run python scripts/check_cli_no_web.py

check: lint fmt-check typecheck check-stateless check-cli-no-web

# ── Dev servers ───────────────────────────────────────────────────────────────

api: dev-api

dev-api:
    uv run --package pixfabrica-api uvicorn pixfabrica_api.main:app --reload --host 0.0.0.0 --port 8000

dev-web:
    cd web && pnpm dev

# ── CLI ───────────────────────────────────────────────────────────────────────

# Render a graph: just render graph.json output.mp4
render graph output="output.mp4":
    uv run pixfabrica render {{ graph }} --output {{ output }}
