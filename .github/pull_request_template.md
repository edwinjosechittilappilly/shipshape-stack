<!--
Title: Conventional Commits, `type(scope)!: subject`. Types: feat fix docs chore refactor test ci perf build revert style security.
Lower-case subject, no trailing period, at most 72 characters. Example: `feat(api): add item search`.

Keep it short and factual. `scripts/ci/check_pr.py` validates the headings below on every PR: Summary, Changes and
Verification must be filled in. HTML comments like this one do not count as content. Delete sections that do not apply
(Screenshots for a server-only change). Full standard: .agents/skills/pull-request/SKILL.md
-->

## Summary

<!-- 1-3 sentences: what changes for users or operators, and why. Outcome first. -->

## Linked issue

<!-- `Closes #123` (or `Refs #123`). Write `None` if there is no issue. -->

## Changes

<!-- Group by area. One line per behaviour, not per file. -->

- **Backend:**
- **Frontend:**
- **Infra / CI / Docs:**

## Verification

<!--
List every check you ran, pass or fail, with the command. Explain each failure (pre-existing on main? environment?).
Mark checks you did not run with `skipped` and the reason. Never claim a check you did not run.
-->

| Check | Command | Result |
| --- | --- | --- |
| Lint, types, unit tests | `make check` | |
| Integration tests | `make test-integration` | |
| E2E (mocked API) | `make test-e2e` | |

## Screenshots

<!-- Required for UI changes: before/after of the changed surface in a realistic state. Never commit screenshots to the repo. -->

## Risk and rollback

<!-- Blast radius, migrations (are they reversible?), feature flags, how to roll back. Required when the title has `!`. -->

## Out of scope

<!-- What this PR deliberately does not do. Remove if none. -->

## Checklist

- [ ] Tests added or updated (or not needed, and why)
- [ ] Docs updated (README, `docs/`, `AGENTS.md`, API docs)
- [ ] No secrets, tokens or personal data in the diff
- [ ] Screenshots attached for UI changes
- [ ] Database migration is reversible (`downgrade` works) or there is no migration
- [ ] Breaking changes are marked with `!` in the title and described under Risk and rollback
