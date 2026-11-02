from typing import Annotated

from fastapi import APIRouter, Path, Response, status

from app.api.deps import ItemServiceDep
from app.schemas import ItemCreate, ItemRead, ItemUpdate

router = APIRouter(prefix="/api/v1/items", tags=["items"])

# Postgres `integer` tops out at 2**31-1; reject larger ids as 422 instead of failing in the driver.
ItemId = Annotated[int, Path(ge=1, le=2**31 - 1)]


@router.get("")
def list_items(service: ItemServiceDep) -> list[ItemRead]:
    return [ItemRead.model_validate(item) for item in service.list_items()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_item(data: ItemCreate, service: ItemServiceDep) -> ItemRead:
    return ItemRead.model_validate(service.create_item(data))


@router.get("/{item_id}")
def get_item(item_id: ItemId, service: ItemServiceDep) -> ItemRead:
    return ItemRead.model_validate(service.get_item(item_id))


@router.patch("/{item_id}")
def update_item(item_id: ItemId, data: ItemUpdate, service: ItemServiceDep) -> ItemRead:
    return ItemRead.model_validate(service.update_item(item_id, data))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: ItemId, service: ItemServiceDep) -> Response:
    service.delete_item(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
