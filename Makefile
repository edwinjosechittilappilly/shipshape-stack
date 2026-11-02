# Root task runner. Every CI job calls one of these targets, so "it passed locally" means the same thing as
# "it passed in CI". Package-specific logic lives in backend/Makefile and frontend/Makefile; this file only delegates.

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help
MAKEFLAGS += --no-print-directory

COMPOSE ?= docker compose
PACKAGES := backend frontend

.PHONY: help setup lint format typecheck test test-integration test-e2e test-e2e-fullstack check doctor audit \
        db-up up down logs build security helm-lint kind-e2e pr-check hooks-test

help: ## List targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install toolchains and dependencies for every package
	@for p in $(PACKAGES); do $(MAKE) -C $$p setup; done

lint: ## Check-only lint for every package and repo scripts (never writes)
	@for p in $(PACKAGES); do $(MAKE) -C $$p lint; done
	find scripts -name '*.sh' -print0 | xargs -0 shellcheck

format: ## Auto-format every package (writes files)
	@for p in $(PACKAGES); do $(MAKE) -C $$p format; done

typecheck: ## Static type checks
	@for p in $(PACKAGES); do $(MAKE) -C $$p typecheck; done

test: ## Fast unit tests (no network, no containers)
	@for p in $(PACKAGES); do $(MAKE) -C $$p test; done
	python3 -m unittest discover -s scripts/ci/tests -t . -q
	python3 -m unittest discover -s .agents/skills/repo-audit/tests -t .agents/skills/repo-audit -q

test-integration: db-up ## Backend integration tests against a real Postgres
	$(MAKE) -C backend test-integration

test-e2e: ## Playwright against Vite with a mocked API (no backend needed)
	$(MAKE) -C frontend test-e2e

test-e2e-fullstack: up ## Playwright against the full compose stack
	$(MAKE) -C frontend test-e2e-fullstack

check: lint typecheck test doctor audit ## The pre-push gate: lint + typecheck + unit tests + React Doctor + repo score

doctor: ## React Doctor health scan of the frontend (fails on error-severity findings)
	$(MAKE) -C frontend doctor

audit: ## Score this repo against its own best-practice rubric (fails below 90)
	python3 .agents/skills/repo-audit/scripts/audit.py . --format text --min-score 90

db-up: ## Start only Postgres and wait until healthy
	$(COMPOSE) up -d --wait postgres

up: ## Build and start the full stack (http://localhost:8080)
	$(COMPOSE) up -d --build --wait

down: ## Stop the stack and delete volumes
	$(COMPOSE) down -v --remove-orphans

logs: ## Tail stack logs
	$(COMPOSE) logs -f --tail=100

build: ## Build container images (app-backend:local, app-frontend:local)
	$(COMPOSE) build

security: ## Trivy: vulnerabilities, secrets, IaC misconfig, images (same policy as CI)
	scripts/security/trivy-scan.sh

helm-lint: ## Lint and render the Helm chart
	helm lint deploy/helm/app --strict
	helm template app deploy/helm/app >/dev/null

kind-e2e: ## Deploy to a local kind cluster and smoke-test it
	scripts/kind-e2e.sh

pr-check: ## Validate a PR title/body locally: make pr-check TITLE="feat: x" BODY=path/to/body.md
	python3 scripts/ci/check_pr.py --title "$(TITLE)" --body-file "$(BODY)"

hooks-test: ## Self-test the agent hook scripts
	scripts/agent-hooks/test-hooks.sh
