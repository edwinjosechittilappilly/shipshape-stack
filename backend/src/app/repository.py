"""Persistence boundary. The service depends on the Protocol; unit tests use an in-memory fake."""

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Item


class ItemRepository(Protocol):
    def list_all(self) -> Sequence[Item]: ...
    def get(self, item_id: int) -> Item | None: ...
    def add(self, item: Item) -> Item: ...
    def save(self, item: Item) -> Item: ...
    def delete(self, item: Item) -> None: ...


class SqlItemRepository:
    """SQLAlchemy implementation. Each write is its own transaction (one request = one change)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self) -> Sequence[Item]:
        # id breaks ties between rows created in the same instant.
        stmt = select(Item).order_by(Item.created_at.desc(), Item.id.desc())
        return self._session.scalars(stmt).all()

    def get(self, item_id: int) -> Item | None:
        return self._session.get(Item, item_id)

    def add(self, item: Item) -> Item:
        self._session.add(item)
        self._session.commit()
        return item

    def save(self, item: Item) -> Item:
        self._session.commit()  # `item` is session-attached; its changes are already tracked
        return item

    def delete(self, item: Item) -> None:
        self._session.delete(item)
        self._session.commit()
