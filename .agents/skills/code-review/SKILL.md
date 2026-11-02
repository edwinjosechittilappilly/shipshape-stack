---
name: code-review
description: "Use when reviewing a diff, branch or pull request (including your own before opening a PR): severity rubric, review checklist, how to write a finding, and the output format. Also use when acting on review findings someone else wrote."
---

# Code review

> **Outside ShipShape?** `make` targets, paths and labels here come from the
> [ShipShape template](https://github.com/edwinjosechittilappilly/shipshape-stack). In another repo, use its own
> task runner, test folders and labels (see its `AGENTS.md`/`CONTRIBUTING.md`). Resolve the base branch first
> (`gh repo view --json defaultBranchRef -q .defaultBranchRef.name`) and use it wherever this skill says `main`.
> Keep the rules, swap the names, and never invent a command that does not exist.

Review the change, not the author. The goal is to find what would hurt in production or in six
months, with evidence, and say so briefly. If you wrote the code, review it *as a stranger*: re-read
the diff cold, and run the checks instead of trusting memory.

## How to review

1. **Scope**: `git diff --stat origin/main...HEAD` (or `gh pr diff <n>`). Read the PR description / linked
   issue / plan to learn the *intent*, then judge whether the diff achieves it - and only it.
2. **Read whole files around each hunk**, not just the hunk. Callers and callees matter.
3. **Try to falsify**: run `make check`, the relevant test level, or write a quick failing test for a suspicion.
   A reproduced bug beats an opinion.
4. **Walk the checklist** below; skip items that clearly do not apply, but say you skipped.
5. **Write findings** in the format below; then give a verdict.

## Severity rubric

| Level | Meaning | Merge? |
| --- | --- | --- |
| **blocker** | Wrong behaviour, data loss/corruption, security hole, secret committed, broken build/migration, breaking API change without notice | No |
| **major** | Likely bug or regression, missing test for new behaviour/failure path, irreversible migration, missing error handling at a boundary, significant maintainability cost | Fix before merge |
| **minor** | Real but low-impact: naming that misleads, small duplication, weak error message, missing log context, doc gap | Fix or follow-up issue |
| **nit** | Taste/style the tools do not enforce. Prefix `nit:`; never block on these | Author's call |

When unsure between two levels, pick the lower and explain; do not inflate. Do not report what the
formatter/linter/type-checker already enforces (CI will).

## Checklist

### Correctness

- [ ] Does it do what the issue/plan says, including edge cases (empty, max length, unicode, duplicates, concurrency)?
- [ ] Error paths handled at boundaries; no swallowed exceptions; no `None`/`undefined` assumptions
- [ ] Off-by-one, time zones (store tz-aware UTC), ordering without `ORDER BY`, transactions committed/rolled back

### Security

- [ ] No secrets/tokens/`.env` in the diff, logs or error messages; no new broad permissions
- [ ] Input validated at the boundary; SQL via parameters/ORM, never string-built; output encoded (no `dangerouslySetInnerHTML` with user data)
- [ ] AuthN/Z unchanged or explicitly reasoned; CORS/CSP not loosened; new dependency vetted (maintained, licence, pinned)
- [ ] Workflows: actions pinned by SHA, `permissions:` minimal, no untrusted input interpolated into `run:`

### Tests

- [ ] New behaviour has a test that would fail without the change; bug fixes have a regression test
- [ ] Tests assert behaviour, not wiring; right level (`docs/testing.md`); no sleeps, no shared state, no skipped/disabled tests
- [ ] Failure paths covered (404/422/503, error UI state)

### Migrations and data

- [ ] Alembic revision present, has a working downgrade, matches models (drift test), safe on a populated table (expand/contract, no long locks)
- [ ] Backfills idempotent; destructive steps in a later PR than the code that stops using the data

### Observability and operations

- [ ] Meaningful log lines with context (no secrets); errors surface with a status code and `detail`
- [ ] Health/readiness unaffected; new config documented in `.env.example` and wired in compose/Helm
- [ ] Resource, timeout and retry behaviour considered for new outbound calls

### API compatibility

- [ ] Response/field/status changes are additive, or flagged `!` + `breaking-change` with migration notes; versioned path respected
- [ ] Frontend and backend contract (`docs/architecture.md`) still agree; OpenAPI/types updated

### Docs and hygiene

- [ ] README/docs/CHANGELOG/ADR updated when behaviour, commands or decisions changed
- [ ] Diff contains only the intended change: no drive-by refactors, debug output, commented-out code, stray files
- [ ] PR title/description/labels accurate (`pull-request` skill)

## Writing a finding

One finding = one problem. Include **where**, **what**, **why it matters**, **suggested fix**; keep it short and kind.

```markdown
**major** `backend/src/app/service.py:48` - `update_item` commits before validating `title`, so a 422 leaves a half-applied row.
Why: the API returns 422 but the `done` flag was already persisted (reproduced: PATCH `{"done":true,"title":""}`).
Fix: validate first, or wrap in one transaction; add an integration test asserting no change on 422.
```

Good findings are specific (`path:line`), evidenced (command output, failing test), and actionable.
Bad: "This is confusing." / "Consider refactoring." / "Why not use X?" (without saying what breaks).
Praise is allowed where something is genuinely clever or safe - one line, not filler.

## Output format

```markdown
## Review of <branch or #PR> against <base>
Checked: <what you ran/read: make check, integration tests, files...>

### Blockers
- ...
### Major
- ...
### Minor
- ...
### Nits
- nit: ...

**Verdict:** approve | approve-with-nits | changes-requested
```

Omit empty sections; if there are no findings say "No findings" and list what you verified. When posting to
GitHub use `gh pr review <n> --comment -F review.md` (or `--request-changes` for blockers/majors on an agent
reviewer's behalf). **Agents never `--approve`**; approval is a human CODEOWNER's job.

## Acting on findings (as the author)

Fix blockers and majors; address minors or file a follow-up issue; ignore nits unless trivial. For each
finding either change code or reply with evidence why not. Re-run the checks that covered the area, push,
re-request review. Disagreement you cannot settle with evidence -> label `status: needs-human`.
