# Frontend task runner (delegated to by the root Makefile and called directly by CI).
# Thin wrappers over npm scripts so there is one definition of each check.

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

.PHONY: help setup lint format typecheck test build doctor test-e2e test-e2e-fullstack playwright-install

help: ## List targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install dependencies exactly as locked (npm ci)
	npm ci

lint: ## Check-only: ESLint (zero warnings) + Prettier
	npm run lint
	npm run format:check

format: ## Rewrite files with Prettier
	npm run format

typecheck: ## tsc --noEmit (strict)
	npm run typecheck

doctor: ## React Doctor: React-specific correctness/perf/security scan (fails on errors)
	npm run doctor

test: ## Vitest unit/component tests
	npm test

build: ## Type-check and produce dist/
	npm run build

# Browsers are not an npm dependency, so they are installed separately. CI runners also need the OS libraries.
playwright-install: ## Install Chromium for Playwright (adds OS deps when CI=true)
	npx playwright install $(if $(filter true,$(CI)),--with-deps) chromium

test-e2e: ## Playwright `mocked` project (starts Vite, stubs /api)
	npm run test:e2e

test-e2e-fullstack: ## Playwright `fullstack` project against E2E_BASE_URL (default http://localhost:8080)
	npm run test:e2e:fullstack
