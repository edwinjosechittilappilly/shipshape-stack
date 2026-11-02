"""Integration fixtures: a real Postgres, migrated with Alembic into a throwaway database.

Design notes (the why):
- DATABASE_URL points at a *server*; each session creates its own database on it, migrates it with
  the real Alembic revisions, and drops it at the end. Runs never see each other's data and never
  touch the database a developer is using.
- Tests are isolated by TRUNCATE, not rollback, because the app commits for real; rollback-based
  isolation would hide commit bugs.
- If Postgres is unreachable the whole run aborts with a clear message. There are no silent skips:
  a green run must mean the database was actually exercised.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.main import create_app


def alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")  # relative to backend/, where pytest and `make` run
    config.attributes["database_url"] = database_url
    return config


def _server_url() -> URL:
    return make_url(Settings().database_url)


@contextmanager
def temporary_database() -> Iterator[str]:
    """Create an empty database on the configured server; drop it on exit. Yields its URL."""
    server = _server_url()
    name = f"test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(server, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except OperationalError as exc:
        admin.dispose()
        pytest.exit(
            "Integration tests need PostgreSQL but could not connect to "
            f"{server.render_as_string(hide_password=True)}.\n"
            "Start one (e.g. `make db-up`) or set DATABASE_URL, then re-run.\n"
            f"Driver error: {exc.orig}",
            returncode=2,
        )
    try:
        yield server.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with temporary_database() as url:
        command.upgrade(alembic_config(url), "head")
        yield url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE items RESTART IDENTITY"))


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    app = create_app(Settings(database_url=database_url))
    with TestClient(app) as test_client:
        yield test_client
