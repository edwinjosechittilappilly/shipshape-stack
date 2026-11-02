---
name: pull-request
description: "Use when opening, updating or responding to review on a pull request: branch, conventional title, description headings, the Verification table, screenshots, sizing and splitting, draft vs ready, labels (including agent labels), and replying to review comments."
---

# Pull request

> **Outside ShipShape?** `make` targets, `scripts/ci/check_pr.py`, `.github/pull_request_template.md`, the
> headings and labels here come from the [ShipShape template](https://github.com/edwinjosechittilappilly/shipshape-stack).
> In another repo, follow its own PR template, checks and labels (see its `.github/` and `CONTRIBUTING.md`), and
> resolve the base branch (`gh repo view --json defaultBranchRef -q .defaultBranchRef.name`) wherever this skill
> says `main`. If a file or check does not exist there, skip it and say so; never invent one.

A PR is the only durable record of what was verified and why. CI enforces the title and headings
(`scripts/ci/check_pr.py`), but reviewers (human and AI) judge the *content*. Write for someone
who has not seen your session.

## Workflow

1. **Branch from fresh `main`**: `git fetch origin main && git switch -c <type>/<issue>-<kebab-slug> origin/main`
   (e.g. `feat/42-item-search`). One concern per PR.
2. **Size it.** Target < 400 changed lines (`size/M` or smaller). If larger: split along the plan's
   slices, land refactors separately from behaviour changes, and put generated files / lockfiles in
   the PR that causes them. Over `size/L` with no plan slice justifying it -> split before review.
3. **Run the verification ladder** from `AGENTS.md` up to the rung your change needs; always
   `make check`. Keep the real output: you will summarise it, not paraphrase from memory.
4. **Self-review** the diff with the `code-review` skill. Fix blockers/majors first.
5. **Write title + body** (below) and validate: `make pr-check TITLE="..." BODY=/tmp/pr-body.md`.
6. **Push and open**: `git push -u origin HEAD`, then
   `gh pr create --base main --title "..." --body-file /tmp/pr-body.md [--draft]`.
7. **Label** (below), then watch CI (`gh pr checks --watch`). Red CI -> `ci-triage` skill.

## Title

Conventional Commits, validated by CI: `type(scope)!: subject`

- types: `feat fix docs chore refactor test ci perf build revert style security`
- subject starts lower-case, imperative, no trailing period, whole title <= 72 chars
- `!` marks a breaking change (also add label `breaking-change` and a `## Risk and rollback` note)
- squash-merge makes the title the commit on `main`, so make it say what changed for a reader of the log

| Bad | Good |
| --- | --- |
| `Fix bug` | `fix(backend): return 404 when patching a missing item` |
| `feat: Added a new search feature for items.` | `feat(frontend): filter items by title` |
| `updates` | `chore: bump ruff to 0.9` |

## Body

Use `.github/pull_request_template.md`. Required headings (exact): `## Summary`, `## Changes`,
`## Verification`. Also fill `## Linked issue`, `## Screenshots` (UI changes), `## Risk and rollback`,
`## Out of scope`, `## Checklist`.

- **Summary**: 1-3 sentences, user-visible outcome first, then why. No file lists.
- **Linked issue**: `Closes #42`. No issue? say `none` and why (trivial fix, dependency bump).
- **Changes**: behaviours grouped by area (Backend / Frontend / Infra / Docs), not file names.
- **Verification**: a table of what you actually ran. Counts, not adjectives. Mark skipped rungs `n/a` with the reason.

  ```markdown
  | Check | Result | Notes |
  | --- | --- | --- |
  | `make check` | pass | backend 54 tests, frontend 31 tests |
  | `make test-integration` | pass | 12 tests, Postgres 17 |
  | `make test-e2e` | pass | 8 tests, mocked project |
  | `make test-e2e-fullstack` | n/a | no API contract change |
  | `make -C frontend doctor` | pass | React Doctor, no errors (frontend changes only) |
  | `make kind-e2e` | n/a | chart untouched |
  ```

  Never claim a check you did not run. A failure you did not cause: say so and show it fails on
  `main` too (`git worktree add /tmp/base origin/main`, run it there). Unexplained failures block.
- **Risk and rollback**: what could break, how you would notice, how to undo (revert? flag? down-migration?).
- **Out of scope**: things a reviewer might expect but you deliberately left out.

Bad Summary: "Updated some files to improve items." Good: "Items can now be filtered by title in the
list view. Needed because lists over ~50 items were unusable; the filter runs client-side, no API change."

## Screenshots policy

- Required for any visible UI change (before/after when it modifies existing UI); skip for backend-only.
- Capture from a production build or `make up` (`http://localhost:8080`), not a dev server; use
  realistic data and show the changed state (not an empty page), with a one-line bold caption each.
- **Never commit screenshots to the repo.** Attach them by dragging into the PR description or
  comment (GitHub hosts them), or link CI artifacts. Delete throwaway specs you wrote for capturing.

## Draft vs ready

Open as **draft** when: CI is red or not yet run, you want early direction, the plan is not accepted,
or you are waiting on a dependency PR. Mark **ready for review** only when `make check` is green
locally, the body is complete, and you have self-reviewed. Do not request review on a red PR.

## Labels

Apply by hand if automation has not (`gh pr edit <n> --add-label "..."`):

- type from the title (feat -> `type: feature`, fix -> `type: bug`, ...); `breaking-change` for `!`
- area: `area: backend|frontend|infra|ci|docs|tests|agents` (every area touched)
- size is set automatically (`size/XS`..`size/XL`)
- agents add `agent: authored` to PRs they open; add `agent: review` to request an AI review pass;
  `run: kind-e2e` when the change touches `deploy/`, Dockerfiles or `scripts/kind-e2e.sh`
- stuck? `status: needs-human` and a comment saying exactly what is needed. Finished and green:
  `status: ready-to-merge` (humans, or an agent only where `docs/agents/self-managed-prs.md` allows)

## Responding to review

1. Read every comment before changing anything; group them by theme.
2. Fix what is right in new commits (no force-push once review started; squash-merge tidies history).
   Push back with evidence when a comment is wrong - a failing test or a doc link, not opinion.
3. Reply to **each** thread: what you changed (commit sha) or why not. Resolve a thread only after the
   fix is pushed; the reviewer resolves threads for disputed points.
4. Comments that need design change or are out of scope -> open a follow-up issue, link it, say so.
5. Re-request review (`gh pr edit <n> --add-reviewer <user>` or label `agent: review`) after pushing.
6. Update the Verification table when results change.

## Checklist before marking ready

- [ ] Title passes `make pr-check`; body has the required headings with real content
- [ ] `make check` green locally plus every rung the change needs
- [ ] Tests added/changed for behaviour; migrations reversible
- [ ] No secrets, no `.env`, no stray files (`git status`, `git diff --stat`)
- [ ] Docs/CHANGELOG updated when behaviour or commands changed
- [ ] Labels set, issue linked, no unrelated changes in the diff
