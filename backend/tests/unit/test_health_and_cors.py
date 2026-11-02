from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import get_session


class _FailingSession:
    def execute(self, *_: object, **__: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))


class _HealthySession:
    def execute(self, *_: object, **__: object) -> None:
        return None


def test_healthz_never_touches_the_database(client: TestClient) -> None:
    # No session override and an unreachable DATABASE_URL: liveness must still be 200.
    response = client.get("/healthz")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


def test_readyz_ready_when_database_answers(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_session] = lambda: _HealthySession()
    response = client.get("/readyz")
    assert (response.status_code, response.json()) == (200, {"status": "ready"})


def test_readyz_503_when_database_is_down(app: FastAPI, client: TestClient) -> None:
    def failing() -> Iterator[_FailingSession]:
        yield _FailingSession()

    app.dependency_overrides[get_session] = failing
    response = client.get("/readyz")
    assert (response.status_code, response.json()) == (503, {"status": "unavailable"})


def test_readyz_503_against_a_truly_unreachable_database(client: TestClient) -> None:
    # Port 1 refuses connections: exercises the real engine, driver error path and connect timeout.
    assert client.get("/readyz").status_code == 503


@pytest.mark.parametrize(
    ("origin", "allowed"), [("http://allowed.example", True), ("http://evil.example", False)]
)
def test_cors_only_echoes_configured_origins(
    client: TestClient, origin: str, allowed: bool
) -> None:
    response = client.get("/healthz", headers={"Origin": origin})
    assert ("access-control-allow-origin" in response.headers) is allowed
