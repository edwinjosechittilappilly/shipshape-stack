import pytest
from pydantic import ValidationError

from app.schemas import ItemCreate, ItemUpdate


def test_title_is_trimmed() -> None:
    assert ItemCreate(title="  buy milk \n").title == "buy milk"


@pytest.mark.parametrize("title", ["", "   ", "\t\n"])
def test_blank_title_is_rejected(title: str) -> None:
    with pytest.raises(ValidationError):
        ItemCreate(title=title)


def test_title_length_boundary_is_200() -> None:
    assert len(ItemCreate(title="x" * 200).title) == 200
    with pytest.raises(ValidationError):
        ItemCreate(title="x" * 201)


def test_length_is_measured_after_trimming() -> None:
    assert len(ItemCreate(title=" " + "x" * 200 + " ").title) == 200


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ItemCreate.model_validate({"title": "ok", "done": True})


def test_update_allows_partial_bodies() -> None:
    assert ItemUpdate().model_dump(exclude_none=True) == {}
    assert ItemUpdate(done=True).model_dump(exclude_none=True) == {"done": True}


def test_update_applies_the_same_title_rules() -> None:
    with pytest.raises(ValidationError):
        ItemUpdate(title="  ")
