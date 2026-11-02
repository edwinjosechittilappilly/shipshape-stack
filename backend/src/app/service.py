"""Business rules for items, independent of HTTP and of the database."""

from collections.abc import Sequence

from app.models import Item
from app.repository import ItemRepository
from app.schemas import ItemCreate, ItemUpdate


class ItemNotFoundError(Exception):
    def __init__(self, item_id: int) -> None:
        super().__init__(f"Item {item_id} not found")
        self.item_id = item_id


class ItemService:
    def __init__(self, repository: ItemRepository) -> None:
        self._repository = repository

    def list_items(self) -> Sequence[Item]:
        return self._repository.list_all()

    def get_item(self, item_id: int) -> Item:
        item = self._repository.get(item_id)
        if item is None:
            raise ItemNotFoundError(item_id)
        return item

    def create_item(self, data: ItemCreate) -> Item:
        return self._repository.add(Item(title=data.title, done=False))

    def update_item(self, item_id: int, data: ItemUpdate) -> Item:
        item = self.get_item(item_id)
        if data.title is not None:
            item.title = data.title
        if data.done is not None:
            item.done = data.done
        return self._repository.save(item)

    def delete_item(self, item_id: int) -> None:
        self._repository.delete(self.get_item(item_id))
