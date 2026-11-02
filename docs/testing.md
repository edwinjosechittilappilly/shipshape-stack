# Testing

Tests exist to let us change code with confidence and to give agents a fast, trustworthy feedback loop. The goal is
the *cheapest test that can fail for the right reason*, not the most tests.

## The pyramid for this repository

```mermaid
flowchart TB
    kind["kind-e2e (opt-in, minutes)<br/>deploys the Helm chart to a real cluster"]
    full["e2e-fullstack (CI, ~1 min)<br/>Playwright against the compose stack"]
    mocked["e2e-mocked (every PR, seconds)<br/>Playwright + Vite, API stubbed"]
    integ["integration (every PR)<br/>backend + real Postgres"]
    unit["unit (every push, sub-second each)<br/>backend pytest, frontend Vitest, scripts/ci tests"]
    kind --- full --- mocked --- integ --- unit
```

Many fast tests at the bottom, few slow ones at the top. Move a check *down* the pyramid whenever it can still fail for the
reason you care about.

| Level | Where | Runs against | Command | When it runs |
| --- | --- | --- | --- | --- |
| Unit (backend) | `backend/tests/unit/` | Pure code, in-process fakes at true boundaries only | `make -C backend test` | `make check`, every PR |
| Unit (frontend) | `frontend/src/**/*.test.tsx` | Components via Testing Library, `fetch` stubbed | `make -C frontend test` | `make check`, every PR |
| Unit (repo scripts) | `scripts/ci/tests/` | `unittest` for CI helper scripts | `python3 -m unittest discover -s scripts/ci/tests -t .` | `make test`, every PR |
| Integration | `backend/tests/integration/` | FastAPI app + real Postgres (no DB mocks) | `make test-integration` | Every PR (Postgres service container) |
| E2E mocked | `frontend/e2e/` project `mocked` | Real browser + Vite dev server, `/api` stubbed with `page.route` | `make test-e2e` | Every PR |
| E2E full-stack | `frontend/e2e/` project `fullstack` | Real browser + compose stack on `E2E_BASE_URL` (default `http://localhost:8080`) | `make test-e2e-fullstack` | Every PR (main CI) |
| Kind | `scripts/kind-e2e.sh` | Helm chart on a throwaway kind cluster | `make kind-e2e` | PRs with the `run: kind-e2e` label; always on `main` and scheduled runs (see [`ci.md`](ci.md)) |
| Hooks | `scripts/agent-hooks/test-hooks.sh` | Agent hook scripts | `make hooks-test` | Every PR |

Static checks (`make lint`, `make typecheck`, `pre-commit`, Trivy, `make helm-lint`) are not tests but are part of the same
gate; see [`ci.md`](ci.md) and [`security.md`](security.md).

## Heuristics

1. **Test behaviour at boundaries.** Assert on what a caller can observe: HTTP status and body, rendered accessible UI,
   rows in the database. Not on private functions, call counts, or internal structure. Refactoring should not break tests.
2. **One reason to fail.** A test checks one behaviour and its name says which: `test_create_item_rejects_blank_title`.
   If you need "and" in the name, split it.
3. **Deterministic.** No wall-clock dependence, randomness without a seed, ordering assumptions, shared state between tests,
   or network access outside the declared stack. Inject time and IDs; create unique data per test.
4. **No sleeps.** Wait for a condition: Playwright web-first assertions (`expect(locator).toBeVisible()`), Testing Library
   `findBy*`/`waitFor`, polling with a deadline for external systems. A `sleep` is a flaky test you have not met yet.
5. **Do not test mocks.** If the assertion would pass with the real code deleted, the test is worthless. Mock only what you
   do not own and cannot run cheaply (third-party HTTP APIs); use the real database for anything touching SQL, because
   constraints, transactions, and migrations are the behaviour.
6. **Prefer real collaborators to mocks inside a package.** In-memory fakes with the same contract beat call-recording mocks.
7. **Query like a user.** Use accessible roles and names (`getByRole('button', { name: 'Add' })`), never CSS classes or test ids
   unless nothing accessible exists (then fix the accessibility).
8. **Arrange-Act-Assert, readable top to bottom.** Prefer a little duplication in tests over clever shared helpers that hide the scenario.
9. **Test the failure paths.** Validation errors, 404s, database down (`/readyz` returns 503), empty and error states in the UI.
10. **Write the failing test first for bugs.** The regression test must fail before the fix and pass after.
11. **Coverage is a signal, not a goal.** Use the report to find *untested behaviour*, not to hit a number. A low-value test
    written to raise coverage is a liability. Do not gate merges on a percentage; review diffs for untested branches instead.
12. **Keep tests fast.** Unit suites should finish in seconds so people actually run `make check`; push slow concerns up the
    pyramid and out of the default loop.

## What goes where: decision guide

- Pure logic, validation, formatting → **unit**.
- Anything involving SQL, transactions, migrations, constraints, or the HTTP stack end to end in-process → **integration**.
- UI behaviour that depends on layout, focus, navigation, or browser APIs → **e2e mocked** (deterministic, no backend).
- Contract between UI and API actually working together → **e2e full-stack** (keep to a few critical journeys: add, toggle, delete).
- Chart, probes, security contexts, hooks, Secrets wiring → **kind**.

Skills with step-by-step guidance for agents: [`integration-tests`](../.agents/skills/integration-tests/SKILL.md),
[`playwright-tests`](../.agents/skills/playwright-tests/SKILL.md).

## Running each level

```bash
make check                  # lint + typecheck + unit tests (backend, frontend, repo scripts): run before every push
make -C backend test        # backend unit tests only
make -C frontend test       # frontend unit tests only
make test-integration       # starts Postgres (make db-up), then backend integration tests
make test-e2e               # Playwright, mocked API (first time: make -C frontend playwright-install)
make test-e2e-fullstack     # starts the compose stack (make up), then Playwright against it
make kind-e2e               # needs docker, kind, kubectl, helm; creates and (optionally) removes a cluster
make down                   # stop the stack and remove volumes when you are finished
```

Integration tests read `DATABASE_URL` (default `postgresql+psycopg://app:app@localhost:5432/app`); CI points it at a Postgres service
container. Set `POSTGRES_PORT` if 5432 is taken locally.

## Flaky test policy

A flaky test (passes and fails on the same commit) is a bug in the test or the code, and it erodes trust in every green build.

1. **Do not just re-run.** Re-running hides the problem. A re-run is acceptable only to unblock while you investigate.
2. **Report it.** Open an issue titled `flaky: <test name>` with the failing CI run link, the error, and how often it fails.
3. **Quarantine within a day if it keeps failing.** Mark it skipped with a comment linking the issue
   (`@pytest.mark.skip(reason="flaky, see #123")` / `test.fixme`); never delete it silently and never leave it skipped without an issue.
4. **Fix the cause**: usually a hidden wait (sleep, missing await), shared state, time or ordering dependence, or resource
   contention. Retries in config are a last resort, limited to the e2e layers, and every retried pass is a signal to investigate.
5. **Un-quarantine** in the same PR that fixes it, with a note on the root cause.

Agents that hit a flaky failure in CI follow the same steps (see the [`ci-triage`](../.agents/skills/ci-triage/SKILL.md) skill)
and must not weaken assertions or add sleeps to make it pass.
