import pytest

from app.schemas import ItemCreate, ItemUpdate
from app.service import ItemNotFoundError, ItemService


def test_create_starts_not_done(service: ItemService) -> None:
    item = service.create_item(ItemCreate(title="write tests"))
    assert (item.title, item.done) == ("write tests", False)


def test_list_is_newest_first(service: ItemService) -> None:
    for title in ("first", "second", "third"):
        service.create_item(ItemCreate(title=title))
    assert [i.title for i in service.list_items()] == ["third", "second", "first"]


def test_update_changes_only_provided_fields(service: ItemService) -> None:
    item = service.create_item(ItemCreate(title="a"))
    service.update_item(item.id, ItemUpdate(done=True))
    assert (service.get_item(item.id).title, service.get_item(item.id).done) == ("a", True)
    service.update_item(item.id, ItemUpdate(title="b"))
    assert (service.get_item(item.id).title, service.get_item(item.id).done) == ("b", True)


def test_delete_removes_the_item(service: ItemService) -> None:
    item = service.create_item(ItemCreate(title="a"))
    service.delete_item(item.id)
    with pytest.raises(ItemNotFoundError):
        service.get_item(item.id)


def test_get_missing_item_raises_not_found(service: ItemService) -> None:
    with pytest.raises(ItemNotFoundError, match="Item 42 not found"):
        service.get_item(42)


def test_update_missing_item_raises_not_found(service: ItemService) -> None:
    with pytest.raises(ItemNotFoundError):
        service.update_item(42, ItemUpdate(done=True))


def test_delete_missing_item_raises_not_found(service: ItemService) -> None:
    with pytest.raises(ItemNotFoundError):
        service.delete_item(42)
