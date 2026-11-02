# AGENTS.md

Instructions for coding agents (Claude Code, Codex, Cursor, and anything that reads `AGENTS.md`) and a
fast orientation for humans. Keep it short: details live in `docs/` and in skills (`.agents/skills/`),
which you load on demand. If this file and a doc disagree, the doc is newer - fix this file.

## What this repo is

A full-stack, cloud-native starter template with a tiny "items" (to-do) app as the example domain:
Python 3.13 / FastAPI / SQLAlchemy 2 / Alembic / Postgres 17 backend, React 19 / TypeScript / Vite frontend,
Docker Compose, a Helm chart, OpenTofu, GitHub Actions CI, and tooling so humans and agents share one workflow.

## Map

| Path | What lives there |
| --- | --- |
| `backend/` | FastAPI app (`src/app`), Alembic migrations (`migrations/`), tests (`tests/unit`, `tests/integration`), own `Makefile` |
| `frontend/` | Vite + React app (`src`), Vitest tests, Playwright specs (`e2e/`), nginx config, own `Makefile` |
| `deploy/` | Helm chart `deploy/helm/app`, kind config and dev Postgres `deploy/kind/` |
| `infra/` | OpenTofu/Terraform-compatible IaC |
| `docker-compose.yml` | Local stack: postgres, migrate, backend, frontend (`http://localhost:8080`) |
| `.github/` | Workflows, PR/issue templates, labels (`labels.yml`), CODEOWNERS |
| `scripts/` | `ci/` (PR checks), `security/`, `agent-hooks/` (guardrails for agents), `kind-e2e.sh` |
| `docs/` | `architecture.md`, `conventions.md`, `testing.md`, `ci.md`, `plans/`, `adr/`, `agents/` |
| `.agents/skills/` | Agent skills (`.claude/skills` symlinks here) |

## Commands (run from the repo root)

| Command | What it does |
| --- | --- |
| `make setup` | Install toolchains and dependencies for every package |
| `make check` | **Pre-push gate**: lint + typecheck + unit tests |
| `make lint` / `make format` | Check-only lint / auto-format (writes). Never fix lint by disabling rules |
| `make typecheck` / `make test` | mypy strict + tsc strict / backend pytest, Vitest, `scripts/ci` tests |
| `make test-integration` | Starts Postgres (`db-up`), runs backend integration tests |
| `make test-e2e` | Playwright `mocked` project (Vite, stubbed API; first run: `make -C frontend playwright-install`) |
| `make test-e2e-fullstack` | `make up`, then Playwright `fullstack` project against `http://localhost:8080` |
| `make up` / `make down` / `make logs` | Build + start / stop and wipe volumes / tail the compose stack |
| `make helm-lint` / `make kind-e2e` | Lint + render the chart / deploy to a local kind cluster and smoke test |
| `make security` | Trivy: vulnerabilities, secrets, IaC, images |
| `make pr-check TITLE="..." BODY=file.md` | Validate a PR title and description exactly as CI does |
| `make hooks-test` | Self-test the agent hooks |
| `make -C backend <target>` / `make -C frontend <target>` | Per-package targets (same names; frontend also `build`, `doctor`) |

Frontend extras: `make -C frontend doctor` (React Doctor: React correctness/perf/security; CI runs it on frontend PRs).
Single backend test: `uv run --project backend pytest backend/tests/unit/test_x.py::test_y -x`.
Single Playwright test: `cd frontend && npx playwright test e2e/items.mocked.spec.ts -g "adds"`.

## Verification ladder

Climb only as high as the change requires, but always start at the bottom and never skip a rung you need.

1. **Unit** - `make check` (every change; always before pushing)
2. **Integration** - `make test-integration` (SQL, migrations, API behaviour against real Postgres)
3. **E2E mocked** - `make test-e2e` (UI behaviour; add `make -C frontend doctor` for React changes)
4. **Full stack** - `make test-e2e-fullstack` (UI <-> API <-> DB contract; compose, nginx or Dockerfile changes)
5. **Kind** - `make kind-e2e` (Helm chart, probes, security contexts, migration hook; label PR `run: kind-e2e`)

Details and which test belongs where: `docs/testing.md`. Write the **cheapest test that can fail for the right reason**.

## Definition of done

- [ ] Behaviour matches the issue's acceptance criteria; no unrelated changes in the diff
- [ ] Tests added or updated for behaviour (bug fix = regression test that fails without the fix)
- [ ] `make check` is green, plus every rung of the ladder the change needs; results are in the PR's Verification table
- [ ] Migrations have a working downgrade and pass the drift test; docs / `.env.example` / CHANGELOG updated if behaviour, config or commands changed
- [ ] You reviewed your own diff (`code-review` skill); no secrets, debug output or stray files
- [ ] PR opened per the `pull-request` skill; CI (`ci-success`) is green

## Coding rules

- **Small diffs.** One concern per PR, aim < 400 changed lines. No drive-by refactors, renames or reformatting; open a separate PR.
- **Follow existing patterns** (`docs/conventions.md`) before inventing new ones. Boring beats clever.
- **Tests assert behaviour, not wiring.** No mocks of what you own, no sleeps, no order dependence, no skipped/disabled tests. Query UIs by role and accessible name.
- **Never disable a check** to get green: no `--no-verify`, `# noqa`/`eslint-disable`/`@ts-ignore` without a reason comment and a real need, no `continue-on-error`, no loosened thresholds, no removed tests.
- **No secrets.** Never read, print, copy or commit `.env*` (except `.env.example`), keys, tokens or credentials. Config comes from env vars read in one settings module.
- **Migrations are reversible and backward compatible** (expand/contract). Never edit a merged migration; add a new one. Migrations run as a separate step, never at app start.
- **API/contract changes are additive** or flagged breaking (`!`, `breaking-change`) with notes. Keep `docs/architecture.md` and frontend types in sync.
- **Pin dependencies and actions** (GitHub Actions by commit SHA with a `# vX.Y.Z` comment). Add a dependency only with a reason in the PR.
- **Handle errors at the boundary**; log with context, never secrets; no bare `except`, no `any`.
- **Do not touch** generated files by hand, lockfiles except via the package manager, or other people's open branches.
- Shell scripts must pass `shellcheck`; Markdown passes markdownlint; YAML passes yamllint (`uvx pre-commit run --files <paths>`).

## PR workflow

1. Pick an issue (prefer `agent: ready`); comment the branch name, add `agent: in-progress`. Large/ambiguous work -> `planning` skill first.
2. Branch from fresh `main`: `<type>/<issue>-<kebab-slug>` (e.g. `feat/42-item-search`, `fix/readyz-timeout`).
3. Implement in small commits (Conventional Commits style); run the ladder; self-review.
4. Title: `type(scope)!: subject` (types: feat fix docs chore refactor test ci perf build revert style security; lower-case subject, <= 72 chars).
   Body: `.github/pull_request_template.md` headings with a real Verification table. Validate with `make pr-check`.
5. `git push -u origin HEAD`; open as **draft** until CI is green and self-review is done, then mark ready.
6. Labels: type (`type: feature|bug|docs|chore|refactor|test|ci|perf|security`), area (`area: backend|frontend|infra|ci|docs|tests|agents`),
   **`agent: authored`** on every agent-opened PR, `agent: review` to request an AI review, `run: kind-e2e` when deploy artifacts change,
   `breaking-change` for `!`. Size labels are automatic.
7. Squash-merge only after required checks and review; the PR title becomes the commit. Agents do not merge unless `docs/agents/self-managed-prs.md` allows it.

## Skills (`.agents/skills/<name>/SKILL.md`) - load the one that matches the task

| Skill | Use when |
| --- | --- |
| `pull-request` | Opening/updating a PR or answering review comments |
| `writing-issues` | Filing or refining an issue; deciding whether it is `agent: ready` |
| `planning` | Work spanning packages or PRs, new dependency/datastore, contract or data-model change; writing plans and ADRs |
| `integration-tests` | Writing or debugging backend tests against real Postgres; migrations |
| `playwright-tests` | Writing or debugging browser tests in `frontend/e2e` |
| `code-review` | Reviewing a diff/PR, and self-review before every PR |
| `ci-triage` | A CI check is red |
| `repo-audit` | Auditing/scoring a repo (this one or another) against these practices and planning improvements with this template as the base |

Claude Code also has `/review`, `/ship-pr`, `/triage-ci` commands and a read-only `reviewer` subagent
(`.claude/`). They are thin wrappers over the skills above. Overview: `docs/agents/README.md`.

## Review loop

1. **Self-review** with `code-review`; fix blockers and majors before asking anyone.
2. **AI review** (CodeRabbit via `.coderabbit.yaml`, or label `agent: review`): address each finding with a commit or a reasoned reply.
3. **Human review** by CODEOWNERS is required for merge. Agents never approve a PR (including their own) and never resolve a human's thread.
4. Reply to every thread, push fixes as new commits (no force-push after review starts), re-request review, update the Verification table.

See `docs/agents/review.md`.

## Guardrails (enforced by hooks in `scripts/agent-hooks/`)

Shell commands are screened before they run: force-push, push to `main`/`master`, `git reset --hard`, `git clean -fdx`, `--no-verify`,
`rm -rf /` or `~`, `curl | sh`, reading `.env*`, disabling git hooks, `gh pr merge --admin` and `gh pr review --approve` are blocked with the
safe alternative in the message. Edited files are auto-formatted; before you stop, lint + typecheck run for changed packages.
Read the message and follow it; do not look for a way around a block. See `docs/agents/hooks.md`.

## Escalate: stop, label `status: needs-human`, and say exactly what you need

- Requirements are ambiguous, contradictory or need a product decision; or acceptance criteria cannot be tested
- The change needs credentials, secrets, cloud resources, billing, or access you do not have
- The change touches auth, secrets handling, `.github/workflows`, `infra/`, branch protection, or security policy and no human owner asked for it
- A destructive or irreversible action (data deletion, force-push, dropping a column/table, publishing a release) is required
- The diff would exceed ~400 lines or span unrelated areas and cannot be split
- CI fails and you cannot reproduce it, it fails on `main` too, or the only way to green is to weaken a check
- You have tried two materially different fixes and the same failure remains, or you are going in circles
- A hook blocks something you believe is legitimate

Leave a comment on the issue/PR with: what you did, what you observed (commands + output), what you ruled out, and the decision you need.
Do not guess, do not work around guardrails, and do not leave a PR silently stalled.
