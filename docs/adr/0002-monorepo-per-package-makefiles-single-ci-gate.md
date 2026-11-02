# ADR-0002: Monorepo with per-package Makefiles and a single CI gate

- **Status:** Accepted
- **Date:** 2026-11-01
- **Deciders:** maintainers
- **Related:** [CI guide](../ci.md), [testing guide](../testing.md), [CONTRIBUTING](../../CONTRIBUTING.md)

## Context

The project has a Python backend, a TypeScript frontend, container and Helm definitions, and infrastructure code that evolve
together: an API change touches the backend, the frontend client, the e2e tests, and sometimes the chart. We want:

- atomic, reviewable cross-cutting changes;
- one way to run any check that is identical locally and in CI, for humans and agents;
- branch protection that does not need editing every time a CI job is added, renamed, or made conditional.

## Decision

1. **One repository** holds backend, frontend, deploy, infra, docs, and agent tooling.
2. **Each package owns its tooling behind a Makefile** (`backend/Makefile`, `frontend/Makefile`) exposing the same verbs:
   `setup lint format typecheck test test-integration` (frontend adds `build test-e2e test-e2e-fullstack`). `lint` is check-only;
   `format` writes. The root `Makefile` only delegates and adds cross-package targets (`check`, `up`, `helm-lint`, `kind-e2e`, ...).
3. **CI calls make targets only**, never re-implements commands in YAML, so "passes locally" and "passes in CI" mean the same thing.
4. **A single aggregate job, `ci-success`,** is the only required status check. It `needs` every other job and fails if any
   failed or was cancelled; jobs that are intentionally skipped (path filters, opt-in labels) count as success.

## Options considered

### Option A: Polyrepo

Independent versioning and permissions, but cross-cutting changes need coordinated PRs and a compatibility matrix. Too heavy for one product.

### Option B: Monorepo with a polyglot build tool (Bazel, Nx, Turborepo)

Powerful caching and graph awareness, but a large learning curve and bespoke configuration that agents and newcomers must learn before contributing.

### Option C: Monorepo with plain Makefiles (chosen)

Boring, universally available, self-documenting with `make help`, and trivial for CI and agents to call. Lacks build caching;
acceptable at this size, and a heavier tool can be adopted later behind the same make targets.

### Option D: Require each CI job as a status check

Simple to start, but every new or renamed job means editing branch protection, and path-filtered jobs that skip never report,
which blocks merges.

## Consequences

- Contributors learn one vocabulary (`make check`) and agents can be told the same.
- Adding a CI job means wiring it into `ci-success`'s `needs`; reviewers must check this (it is in the CodeRabbit workflow instructions).
- Package Makefiles are part of the public contract; changing a target name is a breaking change to CI, docs, and skills.
- Without a build cache CI re-runs everything; mitigated by dependency caching and path filters on heavy jobs.
- Revisit if CI exceeds ~15 minutes or if packages need independent release cadences.
