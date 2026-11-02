# Backend

FastAPI + SQLAlchemy 2 + Alembic on PostgreSQL, managed with [uv](https://docs.astral.sh/uv/). Python 3.13.

## Layout

```text
src/app/
  main.py          app factory (CORS, JSON access log, 404 mapping); run with --factory
  config.py        Settings from env: DATABASE_URL, APP_ENV, LOG_LEVEL, CORS_ORIGINS
  log_config.py    structured JSON logging
  db.py            engine + per-request session dependency
  models.py        SQLAlchemy models (source of truth for the ORM)
  schemas.py       Pydantic request/response models (the API contract)
  repository.py    persistence behind a Protocol (SQL implementation here, fake in tests)
  service.py       business rules; raises domain errors, knows nothing about HTTP
  api/             routers: health.py (/healthz, /readyz), items.py, deps.py
migrations/        Alembic revisions (never run at app start)
tests/unit/        fast, no database: schemas, service, HTTP contract with an in-memory repository
tests/integration/ real Postgres: migrations, full HTTP round-trips
```

## Commands

Run from `backend/` (or `make -C backend <target>`; the root `Makefile` delegates here).

| Command                 | What it does                                                           |
| ----------------------- | ---------------------------------------------------------------------- |
| `make setup`            | `uv sync --locked` into `.venv`                                        |
| `make lint`             | `ruff check` + `ruff format --check` (never writes)                    |
| `make format`           | `ruff check --fix` + `ruff format`                                     |
| `make typecheck`        | `mypy` (strict)                                                        |
| `make test`             | unit tests + coverage gate (`fail_under` in `pyproject.toml`)          |
| `make test-integration` | integration tests against Postgres at `DATABASE_URL`                   |
| `make migrate`          | `alembic upgrade head` against `DATABASE_URL`                          |
| `make run`              | dev server with reload on :8000 (database must already be migrated)    |

Coverage is measured (line + branch) on the unit run only and enforced by `fail_under` in
`pyproject.toml`, set just below the current number (~95%). The unit suite deliberately leaves the SQL
repository to the integration suite, which runs without a coverage threshold. Raise `fail_under` when
coverage rises; do not lower it to get green.

Integration tests need a reachable Postgres (`make db-up` from the repo root starts one) and a role allowed
to `CREATE DATABASE`: each run migrates a throwaway database and drops it afterwards. If Postgres is
unreachable the run aborts with a clear error; it never skips silently.

## Add an endpoint

1. Add or change the request/response model in `schemas.py`.
2. Put rules in `service.py` (raise a domain error for failures) and storage in `repository.py`; extend
   the `ItemRepository` Protocol and the in-memory fake in `tests/unit/conftest.py` together.
3. Add the route in `api/` and include the router in `api/__init__.py`. Map new domain errors to HTTP
   status codes in `main.py`.
4. Test the behaviour: a unit test through `TestClient` and, if SQL is involved, an integration test.

## Add a migration

1. Change `models.py`.
2. `uv run alembic revision --autogenerate -m "add due date"` (needs a database at the current head, e.g. after `make migrate`).
3. Review the generated file in `migrations/versions/`: autogenerate misses some changes. Keep the
   `0002_...` numbering style and write a real `downgrade()`.
4. `make test-integration`: it fails if the models and migrations disagree, and checks upgrade/downgrade.

## Image

`docker build -t app-backend:local backend`. Runs as uid 10001 with a read-only root filesystem.
The default command starts uvicorn on 0.0.0.0:8000; run migrations as a separate step:
`docker run --rm -e DATABASE_URL=... app-backend:local alembic upgrade head`.
