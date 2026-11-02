# ADR-0003: Hardened containers and Helm deployment with an external database

- **Status:** Accepted
- **Date:** 2026-11-01
- **Deciders:** maintainers
- **Related:** [architecture](../architecture.md), [deployment guide](../deployment.md), [security guide](../security.md)

## Context

Services in this template are meant to run on shared Kubernetes clusters where restricted Pod Security standards are common.
Containers that run as root or write to their root filesystem are the most common cause of admission failures and the most
exploitable when compromised. Separately, we must decide how the app gets its database and how schema migrations run, because
getting this wrong causes data loss or deployment deadlocks.

## Decision

1. **Containers are non-root and read-only.** Images run as numeric uid 10001 (frontend uses nginx-unprivileged on 8080),
   work with `readOnlyRootFilesystem: true` (writable paths are explicit `emptyDir` mounts), drop all capabilities, forbid
   privilege escalation, and use the runtime-default seccomp profile. The same properties are verified in CI (Trivy config scan,
   `kind-e2e` smoke test running the hardened pod spec).
2. **Deployment is a Helm chart** (`deploy/helm/app`) with secure defaults, resource requests and limits, and liveness
   (`/healthz`) and readiness (`/readyz`) probes with different semantics.
3. **The database is external.** The chart never deploys Postgres for real environments. `DATABASE_URL` is read from a
   Kubernetes Secret that the operator provides. `deploy/kind/` contains a dev-only Postgres manifest for local clusters and CI.
4. **Migrations are a separate step**, never run at app start: a Helm pre-install/pre-upgrade hook Job runs
   `alembic upgrade head` with the backend image; docker compose has an equivalent `migrate` service.
   Migrations must be backwards compatible with the previous release (expand/contract), so rolling updates and rollbacks are safe.

## Options considered

### Option A: Run as root, writable filesystem

Least friction for images; unacceptable security posture and incompatible with restricted clusters.

### Option B: In-cluster Postgres subchart in the app chart

Convenient demos, but couples data lifecycle to the app release and tempts production use of an unmanaged database. Rejected for real environments; kept only as a dev-only manifest.

### Option C: Run migrations on app start

Simple, but races between replicas, needs elevated DB privileges at runtime, delays readiness, and breaks rollbacks. Rejected.

### Option D: Plain Kubernetes manifests or Kustomize

Fewer moving parts, but less parameterisation and weaker linting (`helm lint --strict`, `helm template`) for a reusable template.

## Consequences

- Applications must not write outside declared volumes; libraries needing scratch space (temp files, caches) must be pointed at `/tmp` via an `emptyDir`.
- Operators must provision the database and the Secret before installing; the chart documents the expected key.
- The hook Job adds a step to install and upgrade, and failures stop the rollout before new pods start (the desired behaviour).
- The runtime database role can be least-privileged by splitting a migration credential from the app credential later, without changing this decision.
- Revisit if a platform requires a different packaging (for example GitOps with Kustomize overlays); the container hardening rules stay.
