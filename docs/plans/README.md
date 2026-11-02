# Plans

A plan is a short design document written **before** a non-trivial change: new features that span packages, data model or API
changes, infrastructure changes, migrations, anything where "how do we do this?" has more than one reasonable answer. It makes
the thinking reviewable *before* code exists and tells agents exactly what to build and how to slice the PRs.

Plans are working documents. When a plan contains a decision that is hard to reverse, record it as an [ADR](../adr/README.md)
and link it from the plan.

## When to write one

- Write a plan when the change touches more than one package, introduces a dependency or datastore, changes a public contract,
  or will take more than one PR.
- Skip it for bug fixes and small, obvious changes; the issue and PR description are enough.

## Process

1. Copy [`TEMPLATE.md`](TEMPLATE.md) to `docs/plans/YYYY-MM-DD-short-title.md` (or `NNNN-short-title.md`; pick one and stay consistent).
2. Fill it in. Concrete beats comprehensive: a page or two is typical.
3. Open a PR with the plan only (label `type: docs`) and link the issue. Discuss and iterate there.
4. When agreed, set `Status: Accepted`, link the plan from the issue, and implement it in the PR slices the plan lists.
5. When shipped, set `Status: Implemented` and link the PRs. Plans are kept as history; they are not updated to track later changes.

Agents use the [`planning`](../../.agents/skills/planning/SKILL.md) skill to write and follow plans.

## Index

| Plan | Status |
| --- | --- |
| [Example: item due dates](2026-11-01-example-item-due-dates.md) | Example (not implemented) |
