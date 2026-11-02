# Architecture Decision Records

An ADR captures one significant decision: the context, the options considered, what we chose, and the consequences. It is
the answer to "why is it like this?" six months later, for humans and for agents that have no memory of the discussion.

## When to write one

Write an ADR when a decision is hard to reverse, affects more than one package, or someone will ask why in the future:
adding a datastore or framework, changing the API versioning or deployment model, choosing a security posture, changing CI gating.
Do **not** write one for routine implementation choices; those belong in the PR description.

Start with a [plan](../plans/README.md) if the decision needs exploration; the ADR is the short, final record.

## Process

1. Copy [`0000-template.md`](0000-template.md) to `NNNN-short-title.md` using the next free number.
2. Fill it in, set `Status: Proposed`, and open a PR (label `type: docs`).
3. Discuss in the PR. On merge, set the status to `Accepted` (same PR, or a follow-up if the decision needs more time).
4. **Accepted ADRs are immutable** apart from the status line. To change a decision, add a new ADR that `Supersedes` the old one
   and mark the old one `Superseded by ADR-NNNN`.

Statuses: `Proposed`, `Accepted`, `Rejected`, `Deprecated`, `Superseded by ADR-NNNN`.

## Index

| ADR | Title | Status |
| --- | --- | --- |
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-monorepo-per-package-makefiles-single-ci-gate.md) | Monorepo with per-package Makefiles and a single CI gate | Accepted |
| [0003](0003-hardened-containers-helm-external-database.md) | Hardened containers and Helm deployment with an external database | Accepted |
