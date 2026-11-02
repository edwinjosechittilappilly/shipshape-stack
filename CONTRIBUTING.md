# Contributing

Thanks for helping. This guide is written for humans **and** coding agents; the rules are identical for both. Agents
additionally read [`AGENTS.md`](AGENTS.md) and [`docs/agents/`](docs/agents/README.md).

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Report security problems privately, as described in
[`SECURITY.md`](SECURITY.md), never in a public issue.

## Table of contents

- [Quickstart](#quickstart)
- [Prerequisites](#prerequisites)
- [Everyday commands](#everyday-commands)
- [Workflow](#workflow)
- [Commit messages and PR titles](#commit-messages-and-pr-titles)
- [Pull requests](#pull-requests)
- [Labels](#labels)
- [Review expectations](#review-expectations)
- [Contributing as an agent](#contributing-as-an-agent)
- [Definition of done](#definition-of-done)

## Quickstart

```bash
git clone <your fork or this repo> && cd <repo>
make setup                 # installs backend (uv) and frontend (npm) dependencies
uvx pre-commit install     # commit-time hygiene hooks (formatting, secrets, YAML, shell, workflows, Markdown)
make check                 # lint + typecheck + unit tests: the same fast gate CI runs first
make up                    # full stack in containers: http://localhost:8080
```

## Prerequisites

| Tool | Version | Used for |
| --- | --- | --- |
| [uv](https://docs.astral.sh/uv/) | latest | Python toolchain; installs Python 3.13 for you |
| Node.js + npm | 24 | Frontend build and tests |
| Docker with Compose v2 | recent | `make up`, integration and full-stack tests |
| GNU Make | 3.81+ | Task runner (macOS default is fine) |
| shellcheck | recent | `make lint` on shell scripts |
| helm, kind, kubectl | optional | `make helm-lint`, `make kind-e2e` |

Nothing else needs to be installed globally; every other tool is pinned in a lockfile or in `.pre-commit-config.yaml`.

## Everyday commands

Run `make help` for the authoritative list. The root `Makefile` only delegates to `backend/Makefile` and `frontend/Makefile`,
and every CI job calls the same targets, so a green local run means a green CI run.

| Target | What it does |
| --- | --- |
| `make setup` | Install dependencies for every package |
| `make lint` | Check-only linting (never writes files) |
| `make format` | Auto-format every package (writes files) |
| `make typecheck` | mypy (strict) and `tsc` |
| `make test` | Fast unit tests: no network, no containers |
| `make check` | **Local gate**: `lint` + `typecheck` + `test`. Run before every push |
| `make test-integration` | Backend tests against a real Postgres (starts it via `make db-up`) |
| `make test-e2e` | Playwright against Vite with a mocked API |
| `make test-e2e-fullstack` | Playwright against the real compose stack |
| `make up` / `down` / `logs` | Run, stop (deleting volumes), or tail the full stack |
| `make build` | Build the container images |
| `make security` | Trivy scan with the same policy as CI |
| `make helm-lint` / `make kind-e2e` | Lint the chart / deploy to a local kind cluster and smoke-test |
| `make pr-check TITLE=... BODY=...` | Validate a PR title and body locally |
| `make hooks-test` | Self-test the agent hook scripts |

What to run when: see the test pyramid in [`docs/testing.md`](docs/testing.md).

## Workflow

1. **Find or file an issue.** Small fixes may skip this; anything non-trivial starts with an issue
   (use the issue forms, see [`.agents/skills/writing-issues`](.agents/skills/writing-issues/SKILL.md)). Changes that touch
   architecture, public API, data model, or infra start with a short plan in [`docs/plans/`](docs/plans/README.md) and, once decided,
   an ADR in [`docs/adr/`](docs/adr/README.md).
2. **Branch from `main`.** Name it `<type>/<short-kebab-description>`, optionally with the issue number:
   `feat/42-item-search`, `fix/readyz-timeout`, `docs/testing-guide`. `type` is a Conventional Commit type (below).
3. **Work in small steps.** One logical change per PR. If a PR will exceed roughly 400 changed lines, split it
   (a plan's "PR slicing" section is the place to decide how). Refactors and behaviour changes go in separate PRs.
4. **Write the test first or alongside**, at the cheapest level that can fail for the right reason
   ([`docs/testing.md`](docs/testing.md)).
5. **Run `make check`** (and the heavier targets your change needs) before pushing.
6. **Open a PR** using the template. Keep it draft until the checks you can run locally pass.
7. **Address review** with new commits (no force-push while a review is in progress); the PR is squash-merged.

## Commit messages and PR titles

We use [Conventional Commits](https://www.conventionalcommits.org/): `type(scope)!: subject`.

- Types: `feat` `fix` `docs` `chore` `refactor` `test` `ci` `perf` `build` `revert` `style` `security`.
- Scope is optional and short: `backend`, `frontend`, `helm`, `ci`, `agents`, ...
- Subject: imperative, starts lower-case, no trailing period, whole title at most 72 characters.
- `!` after the type/scope marks a breaking change; explain the migration in the PR body.

Because PRs are squash-merged, **the PR title becomes the commit on `main`**; it is validated by CI
(`scripts/ci/check_pr.py`) and drives the type label and the changelog. Individual commits on the branch may be informal but
SHOULD still follow the format.

Examples: `feat(backend): add item search endpoint`, `fix(frontend): keep focus after adding an item`,
`ci: pin actions by commit sha`, `refactor(backend)!: drop /api/v0 routes`.

## Pull requests

Use the [PR template](.github/pull_request_template.md). The headings are checked by CI, so keep them:

| Heading | Required | Content |
| --- | --- | --- |
| `## Summary` | yes | What and why, in a few sentences |
| `## Linked issue` | no | `Closes #123` |
| `## Changes` | yes | Bullet list of the notable changes |
| `## Verification` | yes | Table of the checks you actually ran and their results |
| `## Screenshots` | no | For UI changes |
| `## Risk and rollback` | no | Blast radius, how to revert, migrations |
| `## Out of scope` | no | What you deliberately did not do |
| `## Checklist` | no | Self-review items |

Rules of thumb:

- Verification is evidence, not a claim: paste the command and outcome. "Not run" is acceptable when explained.
- Never mix unrelated changes. Never commit secrets, `.env` files, or generated build output.
- Database changes ship as Alembic migrations in the same PR and must be backwards compatible with the previous release
  ([`docs/conventions.md`](docs/conventions.md#database-migrations)).
- CI is a single required check, `ci-success`, that aggregates all jobs. Heavy jobs such as `kind-e2e` are opt-in via the
  `run: kind-e2e` label. See [`docs/ci.md`](docs/ci.md).

## Labels

Labels are applied automatically from the PR title and changed paths where possible; fix them by hand if they are wrong.
The source of truth is `.github/labels.yml`.

| Group | Labels |
| --- | --- |
| Type | `type: feature` `type: bug` `type: docs` `type: chore` `type: refactor` `type: test` `type: ci` `type: perf` `type: security`, plus `breaking-change` |
| Area | `area: backend` `area: frontend` `area: infra` `area: ci` `area: docs` `area: tests` `area: agents` |
| Size | `size/XS` (under 10 changed lines) `size/S` (under 50) `size/M` (under 200) `size/L` (under 500) `size/XL` (500 or more) |
| Status | `status: needs-triage` `status: blocked` `status: needs-human` `status: ready-to-merge` |
| Agents | `agent: ready` `agent: in-progress` `agent: authored` `agent: review` (see below) |
| Misc | `dependencies` `good first issue` `help wanted` `run: kind-e2e` |

`size/XL` PRs get pushback; split them.

## Review expectations

- **Every PR needs at least one approving review** from someone other than the author (CODEOWNERS are requested automatically),
  plus a green `ci-success`. Automated review ([CodeRabbit](.coderabbit.yaml), or an agent running the
  [`code-review`](.agents/skills/code-review/SKILL.md) skill) is advisory and never replaces the human approval.
- **Response targets** (business days, best effort for volunteers): first response within 2 days; `size/XS`-`size/S` reviewed
  within 2 days, `size/M`-`size/L` within 4. Authors respond to review comments within 3 days or mark the PR draft.
- PRs with no activity for 60 days are labelled `stale` by a bot and closed 21 days later unless someone comments or removes the label.
- Reviewers: prioritise correctness, security, then tests, then design, then style (style belongs to the formatters).
  Prefix non-blocking comments with `nit:`. Use the heuristics in [`docs/conventions.md`](docs/conventions.md#best-practice-heuristics-for-reviewers-and-agents).
- Authors: do not resolve a reviewer's thread for them; reply with what changed or why not.
- `status: needs-human` means an agent or CI hit something that needs a person's decision; a maintainer picks it up first.

## Contributing as an agent

Agents are first-class contributors and follow the same process, with a few additions:

- Read [`AGENTS.md`](AGENTS.md) first; it is the entry point and is tool-agnostic (Claude Code, Codex, Cursor, and others).
  Detailed guidance, hook behaviour, and the skill catalogue are in [`docs/agents/`](docs/agents/README.md).
- Pick up issues labelled `agent: ready`; set `agent: in-progress` when you start. Open PRs carry `agent: authored`.
  Add `agent: review` to request an AI review pass.
- Use the repo skills in `.agents/skills/` (`pull-request`, `writing-issues`, `integration-tests`, `playwright-tests`,
  `code-review`, `planning`, `ci-triage`) instead of improvising the process.
- Stay inside the issue's scope, verify with real commands, and report only what you ran. If a decision needs a human, stop,
  label `status: needs-human`, and say exactly what is blocked.
- Agents never bypass hooks or CI (`--no-verify`, disabling checks), never force-push shared branches, and never merge their
  own PRs unless the repository's auto-merge policy for `status: ready-to-merge` explicitly allows it.

## Definition of done

A change is done when all of these hold:

- [ ] Behaviour matches the issue's acceptance criteria and is covered by a test that fails without the change.
- [ ] `make check` passes locally, plus any heavier target your change touches (integration, e2e, helm, kind).
- [ ] `ci-success` is green on the PR; no checks were skipped or weakened to get there.
- [ ] Docs are updated (README, `docs/`, API docs, ADR or plan if a decision was made) and `CHANGELOG.md` has an entry for
      user-visible changes.
- [ ] Migrations, config, and env var changes are reflected in `.env.example`, compose, and the Helm chart.
- [ ] No new secrets, warnings, TODOs without an issue link, or dead code; dependencies added are justified in the PR.
- [ ] The PR description's Verification table lists what was run, and the risk and rollback plan is clear for non-trivial changes.
