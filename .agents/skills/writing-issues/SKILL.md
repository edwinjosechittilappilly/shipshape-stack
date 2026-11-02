---
name: writing-issues
description: "Use when creating or refining a GitHub issue (bug report, feature request, or agent-ready task) and when deciding whether an issue is specified well enough to label `agent: ready` for a coding agent to pick up."
---

# Writing issues

An issue is a contract between whoever asks and whoever builds - increasingly a coding agent with no
memory of the conversation. A good issue lets someone start without asking a question.

Use the issue forms in `.github/ISSUE_TEMPLATE/` (`gh issue create --template ...` or the web UI).
Titles: plain language, specific, no type prefix needed ("Deleting an item leaves its checkbox focused", not "Bug").

## Rules for every issue

1. **One problem per issue.** Two problems = two issues linked together.
2. **Say what, why, and how we will know it is done.** Solutions are suggestions, not requirements,
   unless a constraint forces one (say which and why).
3. **Acceptance criteria are testable**: each one is a statement a test or a reviewer can check
   as pass/fail, naming observable behaviour, not implementation.
4. Link context instead of pasting it: related issues, plan (`docs/plans/`), ADR, code paths.
5. Search first (`gh issue list --search "<keywords>"`); comment on a duplicate instead of filing.

## Bug report

```markdown
### What happened
Adding an item with 200 spaces then "x" stores an empty title and returns 201.

### Expected
Titles are trimmed; blank titles are rejected with 422 (contract: 1..200 chars after trimming).

### Steps to reproduce
1. `make up`
2. `curl -s -X POST localhost:8080/api/v1/items -H 'content-type: application/json' -d '{"title":"   "}'`

### Evidence
Response: `201 {"id":7,"title":"", ...}`; logs: `<paste relevant lines>`; commit `abc1234`, backend only.

### Acceptance criteria
- [ ] `POST` with a whitespace-only title returns 422 and creates no row
- [ ] Regression test at the cheapest level that can fail (unit on the schema)
```

A bug without reproduction steps is `status: needs-triage` until someone reproduces it.
Security bugs: **do not file publicly** - follow `SECURITY.md`.

## Feature request

```markdown
### Problem
Users with long lists cannot find an item without scrolling.

### Proposal (optional)
A text box above the list that filters by title as you type.

### Acceptance criteria
- [ ] Typing in the textbox labelled "Filter items" hides items whose title does not contain the text (case-insensitive)
- [ ] Clearing the box shows every item again; no request is sent to the API while filtering
- [ ] With no match the list shows "No items match" (role=status), not the empty state
- [ ] Playwright (mocked) test covers filter, clear, and no-match

### Out of scope
Server-side search, pagination.
```

Large or cross-package features need a plan first (`planning` skill); the issue then links the plan.

## Agent-ready task

An issue is **`agent: ready`** only if ALL of these hold - otherwise leave it for a human to refine:

- [ ] Problem and desired behaviour are unambiguous; no open product question
- [ ] Acceptance criteria are testable and listed as checkboxes
- [ ] Scope is small: one PR, < ~400 changed lines, one or two packages
- [ ] Entry points named (files/modules to start from) and conventions pointed at (`AGENTS.md`, skill to use)
- [ ] Verification stated: which `make` targets must pass, which test level proves it
- [ ] No design decision hidden inside (if there is one, write an ADR/plan first)
- [ ] Touches no sensitive path (auth, secrets handling, `.github/workflows`, `infra/`, migrations) unless a human owner is named
- [ ] Out of scope is explicit, so the agent does not wander

Template:

```markdown
### Task
Reject whitespace-only item titles at the API.

### Context
`backend/src/app/schemas.py` (ItemCreate), contract in `docs/architecture.md`. Follow `AGENTS.md`.

### Acceptance criteria
- [ ] `POST /api/v1/items` with `{"title": "   "}` -> 422, no row created
- [ ] Unit test in `backend/tests/unit/test_schemas.py`; integration test asserts no row

### Verification
`make check` and `make test-integration`

### Out of scope
Frontend validation messages (separate issue).
```

Bad (not ready): "Improve error handling in the backend." - no observable outcome, unbounded scope.
Good: "`GET /api/v1/items/abc` returns 422 with `detail`, not 500." - observable, bounded, testable.

State machine for agent labels: `agent: ready` -> `agent: in-progress` (agent claims it, comments with branch name)
-> PR gets `agent: authored`. See `docs/agents/self-managed-prs.md`.

## Triage hygiene

- New issues start `status: needs-triage`; add `type:` and `area:` labels when triaging.
- Missing info? Ask one concrete question and add `status: blocked`; do not guess.
- Close with a reason (fixed by #PR, duplicate of #N, won't fix + why). Never close silently.
