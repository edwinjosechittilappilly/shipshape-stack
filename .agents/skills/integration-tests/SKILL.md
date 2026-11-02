---
name: integration-tests
description: "Use when writing, changing or debugging backend integration tests (backend/tests/integration): anything touching SQL, transactions, migrations, constraints or the HTTP stack against a real Postgres. Also use to decide whether a test belongs at integration level at all."
---

# Integration tests

An integration test proves that **our code works with a real dependency at a real boundary**: the
FastAPI app, SQLAlchemy, Alembic migrations and Postgres together. It exists because mocks cannot
reproduce constraints, transactions, collation, timestamps with time zones, or migration drift.

Read first: `backend/tests/integration/conftest.py` (fixtures) and `test_items_http.py`,
`test_migrations.py` (style), plus `docs/testing.md` (the pyramid).

## Run

```bash
make db-up                         # Postgres 17 on localhost:5432 (idempotent, waits until healthy)
make test-integration              # does db-up for you, then runs backend/tests/integration
make -C backend test-integration   # same, assuming Postgres is already up
uv run --project backend pytest backend/tests/integration/test_items_http.py -k round_trip -x   # one test
```

`DATABASE_URL` points at a *server*; the session fixture creates a throwaway `test_<uuid>` database,
runs the real Alembic migrations into it and drops it afterwards. If Postgres is unreachable the run
**aborts loudly** - never "fix" that by skipping tests or swapping in SQLite.

## Should this be an integration test?

| Question | Answer -> level |
| --- | --- |
| Pure function / validation / formatting | unit (`backend/tests/unit`) |
| Needs SQL behaviour: ordering, unique/NOT NULL/FK, defaults, tz-aware timestamps, `ON DELETE` | **integration** |
| Needs commit/rollback semantics or concurrency | **integration** |
| Needs a migration (upgrade, downgrade, drift vs models) | **integration** |
| Needs the browser | Playwright, not here |
| Third-party HTTP API | fake the third party at the HTTP boundary; keep the DB real |

## Principles

1. **Real dependencies at the boundary, nothing mocked inside it.** No mocking of sessions, repositories or the DB.
2. **Assert behaviour a caller can observe**: status code + JSON, rows visible through the API or a direct SQL read.
   Not call counts, not private functions.
3. **Isolation by TRUNCATE, not rollback.** The app commits for real; rollback-based isolation hides
   commit bugs. The autouse `_clean_tables` fixture truncates and resets identities before every test.
   New table -> add it to that fixture.
4. **Tests own their data.** Create what you need in the test (through the API, or `engine.begin()` for
   states the API cannot produce). Never rely on rows another test left, test order, or a shared seed.
5. **Data factories over fixtures with hidden state.** Small helpers that return what they created:

   ```python
   def make_item(client: TestClient, title: str = "write tests", *, done: bool = False) -> dict:
       created = client.post("/api/v1/items", json={"title": title}).json()
       if done:
           created = client.patch(f"/api/v1/items/{created['id']}", json={"done": True}).json()
       return created
   ```

   Unique per-test values come from the test (`title=f"{request.node.name}"`), not from `random`/`time` without a seed.
6. **Deterministic time and ordering.** Do not assert on "now"; insert fixed timestamps via SQL when
   testing ordering (see `test_ties_on_created_at_are_ordered_by_id`).
7. **Fast enough to run every PR**: one session database, migrations once, TRUNCATE per test. If a test needs > ~1 s, ask why.

## Naming and shape

- File per boundary: `test_<resource>_http.py`, `test_migrations.py`, `test_<feature>_db.py`.
- Function names state behaviour: `test_list_is_newest_first`, `test_patch_unknown_id_is_404_with_detail`,
  `test_upgrade_then_downgrade_round_trips`. One behaviour per test; "and" in the name = split it.
- Arrange-Act-Assert, visible top to bottom. A few duplicated lines beat a helper that hides the scenario.
- Type hints on fixtures/tests (mypy strict covers tests).

Good:

```python
def test_create_rejects_blank_title(client: TestClient, engine: Engine) -> None:
    response = client.post("/api/v1/items", json={"title": "   "})
    assert response.status_code == 422
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM items")).scalar_one() == 0   # nothing was written
```

Bad (tests wiring, passes with the real code deleted):

```python
def test_create_calls_repository(mocker):
    repo = mocker.patch("app.service.ItemRepository")
    service.create(...)
    repo.add.assert_called_once()
```

## Migrations

Every schema change ships with a migration and these tests must stay green (they run in `make test-integration`):

- models and migrations do not drift (`compare_metadata == []`)
- `upgrade head` -> `downgrade base` -> `upgrade head` round-trips

Write the **downgrade**. For data migrations add a test that seeds old-shape rows, upgrades, and asserts the new shape.
Use expand/contract for anything deployed: add nullable column -> backfill -> enforce -> (later PR) drop old.

## What NOT to test here

- Framework behaviour (that FastAPI returns 422 for a missing field you did not customise)
- Pydantic validation rules in isolation (unit test them)
- Pure logic that needs no database
- The same assertion at three levels - pick the cheapest level that can fail for the right reason
- Performance (separate benchmarks), UI, container/Helm wiring (kind e2e)

## Flake policy

A flaky integration test is a bug in the test or the code, never "just CI".

1. Reproduce: loop the single test (`for i in $(seq 20); do uv run --project backend pytest backend/tests/integration/test_x.py::test_y -x || break; done`), then run the whole file and the whole suite to see whether order or neighbours matter.
2. Find the shared state: leftover rows, ordering without `ORDER BY`, time, ports, a session-scoped fixture mutated by a test.
3. Fix the cause (own your data, add `ORDER BY`, inject time). **Never** add retries, sleeps, `xfail` or skips to get green.
4. If you cannot fix it in the PR: open an issue with logs, label `status: needs-human`, and quarantine only with
   a human's approval and a linked issue + deadline in the skip reason.

## Checklist

- [ ] Runs from clean DB: `make db-up && make test-integration`
- [ ] Passes alone and in the full run (`pytest <file>::<test>`)
- [ ] No mocks of anything inside the boundary; no sleeps; no reliance on ids/time/order unless set by the test
- [ ] Asserts on observable behaviour, includes the failure path (404, 422, constraint violation)
- [ ] New table -> truncate fixture updated; schema change -> migration + downgrade + drift test green
