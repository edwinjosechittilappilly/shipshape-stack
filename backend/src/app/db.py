"""Engine and session plumbing. The engine is lazy: nothing connects until the first query."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

# Fail fast when Postgres is unreachable so /readyz answers 503 quickly instead of hanging a probe.
_CONNECT_TIMEOUT_SECONDS = 3


def create_db_engine(database_url: str) -> Engine:
    return create_engine(
        database_url,
        pool_pre_ping=True,  # transparently replace connections dropped by the DB or a proxy
        connect_args={"connect_timeout": _CONNECT_TIMEOUT_SECONDS},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False: objects stay readable after commit, so responses serialize without
    # an extra SELECT per row.
    return sessionmaker(engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one session per request; closing it rolls back anything uncommitted."""
    with request.app.state.session_factory() as session:
        yield session
