"""Shared FastAPI dependencies. Tests override these to swap real storage for fakes."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.repository import SqlItemRepository
from app.service import ItemService

SessionDep = Annotated[Session, Depends(get_session)]


def get_item_service(session: SessionDep) -> ItemService:
    return ItemService(SqlItemRepository(session))


ItemServiceDep = Annotated[ItemService, Depends(get_item_service)]
