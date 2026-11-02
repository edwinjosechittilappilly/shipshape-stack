---
name: planning
description: "Use before starting any change that spans packages, adds a dependency or datastore, changes a public contract or data model, or will take more than one PR: decide whether a plan or ADR is required, write it from the templates, and slice the work into reviewable PRs."
---

# Planning

Planning is cheap; rework is not. A plan makes the thinking reviewable *before* code exists and
gives agents (and humans) an unambiguous definition of the work and its slices.

## Do I need a plan or an ADR?

| Situation | Artifact |
| --- | --- |
| Bug fix, small obvious change, dependency bump | none - issue + PR description |
| Feature in one package, one PR, clear design | issue with acceptance criteria (`writing-issues`) |
| Touches > 1 package, > 1 PR, new API/data model, new infra, risky migration, several reasonable designs | **plan** in `docs/plans/` |
| Decision hard to reverse or others will ask "why?" later (framework, datastore, auth, versioning, CI gating, deployment model) | **ADR** in `docs/adr/` (often distilled from a plan) |

If you are unsure, write a half-page plan; if it takes more than an hour to write, you needed it.

## Steps

1. **Understand**: read the issue, `docs/architecture.md`, `docs/conventions.md`, existing ADRs/plans, and the
   code you would change. Name what you do not know and find out (read code, run it) before designing.
2. **Copy the template**: `cp docs/plans/TEMPLATE.md docs/plans/YYYY-MM-DD-short-title.md`
   (see `docs/plans/README.md`; worked example: `docs/plans/2026-11-01-example-item-due-dates.md`).
3. **Fill it in** - concrete beats comprehensive, 1-2 pages:
   - *Problem* with evidence; *Goals* as observable outcomes; *Non-goals* to pre-empt scope creep
   - *Options* (at least two real ones) with pros/cons/cost, then *Decision* with the reason it won
   - *Rollout*: migration order (expand/contract), backwards compatibility, config, rollback
   - *Test plan*: which level proves each goal (`docs/testing.md`)
   - *PR slicing*: the ordered list of PRs (below)
   - *Risks / open questions*: unknowns that could change the plan
4. **Open a plan-only PR** (`docs(plans): ...`, label `type: docs`, link the issue). Iterate in review.
   Agents: stop here and wait for a human to accept; do not start implementation on a draft plan.
5. **Record decisions as ADRs** when they are hard to reverse: `cp docs/adr/0000-template.md docs/adr/NNNN-title.md`
   (next free number, `Status: Proposed`); link from the plan. Accepted ADRs are immutable - supersede, don't edit.
6. **Implement slice by slice**, linking the plan in every PR. When a slice teaches you something that changes
   the plan, update the plan in the same PR (or stop and raise it) - never silently diverge.
7. **Close out**: mark the plan `Implemented` with the PR links.

## Slicing a plan into PRs

Each slice is independently reviewable, mergeable and **leaves `main` green and deployable**.

- Order by dependency, riskiest-unknown first (a spike that can kill the plan goes first).
- Typical order: expand schema (migration, backwards-compatible) -> backend behaviour behind unchanged API ->
  API surface -> frontend -> cleanup/contract (drop old column, remove flag).
- One concern per PR: refactors never share a PR with behaviour changes; generated code/lockfiles ride with their cause.
- Target < 400 changed lines per slice; each slice names its own tests and verification rung.
- Use flags or additive APIs so a half-finished feature is invisible to users.
- Write slices as issues (`writing-issues`); well-specified slices get `agent: ready`.

Slice list format in the plan:

```markdown
## PR slicing
1. `feat(backend): add nullable items.due_at column` - migration + downgrade + drift test (integration)
2. `feat(backend): accept and return due_at` - schema/service/API + unit + integration tests
3. `feat(frontend): date picker and overdue badge` - component + mocked e2e test
4. `test: fullstack journey for due dates` - one critical path
```

## Good vs bad

Bad plan: "Add due dates. We'll use a date column and a picker." (no options, no rollout, no test plan, one giant PR)

Good plan: states the problem with evidence, compares nullable-column vs separate-table options, picks one with the reason,
gives the expand/contract rollout and the four slices above, and lists what is explicitly not included (reminders, recurrence).

## Checklist

- [ ] Right artifact chosen (none / issue / plan / ADR)
- [ ] At least two options considered; the decision names the reason
- [ ] Rollout and rollback described; migrations backward compatible
- [ ] Test plan maps each goal to a test level
- [ ] Slices are ordered, each < ~400 lines, each leaves `main` green
- [ ] Plan reviewed and accepted by a human before implementation starts
