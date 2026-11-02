"""Unit-test fixtures: an in-memory repository and an app wired to it. No database involved."""

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_item_service
from app.config import Settings
from app.main import create_app
from app.models import Item
from app.service import ItemService


class InMemoryItemRepository:
    """Behaves like the SQL repository: ids increase, newest first, server-side defaults filled."""

    def __init__(self) -> None:
        self._items: dict[int, Item] = {}
        self._next_id = 1
        self._clock = datetime(2026, 1, 1, tzinfo=UTC)

    def list_all(self) -> Sequence[Item]:
        return sorted(self._items.values(), key=lambda i: (i.created_at, i.id), reverse=True)

    def get(self, item_id: int) -> Item | None:
        return self._items.get(item_id)

    def add(self, item: Item) -> Item:
        item.id = self._next_id
        item.created_at = self._clock
        self._next_id += 1
        self._clock += timedelta(seconds=1)
        self._items[item.id] = item
        return item

    def save(self, item: Item) -> Item:
        return item

    def delete(self, item: Item) -> None:
        del self._items[item.id]


@pytest.fixture
def repository() -> InMemoryItemRepository:
    return InMemoryItemRepository()


@pytest.fixture
def service(repository: InMemoryItemRepository) -> ItemService:
    return ItemService(repository)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://unused:unused@127.0.0.1:1/unused",
        cors_origins=["http://allowed.example"],
    )


@pytest.fixture
def app(settings: Settings, service: ItemService) -> FastAPI:
    application = create_app(settings)
    application.dependency_overrides[get_item_service] = lambda: service
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
