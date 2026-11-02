"""Pydantic v2 request/response models: the public API contract."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.models import TITLE_MAX_LENGTH

# Trim first, then enforce 1..200, so "   " is rejected rather than stored as an empty title.
Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX_LENGTH)
]


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title


class ItemUpdate(BaseModel):
    """PATCH body. Omitted (or null) fields are left unchanged."""

    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    done: bool | None = None


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    done: bool
    created_at: datetime
