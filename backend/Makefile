# Backend tasks. `uv run` keeps everything inside the locked project environment (.venv).

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

.PHONY: help setup lint format typecheck test test-integration run migrate

help: ## List targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Create .venv from uv.lock (fails if the lockfile is stale)
	uv sync --locked

lint: ## Check-only: ruff lint + format check
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto-fix lint issues and format (writes files)
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## mypy --strict
	uv run mypy

test: ## Unit tests with coverage gate (fast, no database)
	uv run pytest --cov

test-integration: ## Integration tests against Postgres at DATABASE_URL (fails if unreachable)
	uv run pytest tests/integration -m integration

run: ## Dev server with reload on :8000 (needs a migrated database)
	uv run uvicorn app.main:create_app --factory --reload --port 8000

migrate: ## alembic upgrade head against DATABASE_URL
	uv run alembic upgrade head
