"""HTTP contract of /api/v1/items, exercised through the real app with an in-memory service."""

from fastapi.testclient import TestClient

BASE = "/api/v1/items"


def test_create_returns_201_and_the_item_shape(client: TestClient) -> None:
    response = client.post(BASE, json={"title": "  buy milk "})
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "title", "done", "created_at"}
    assert (body["title"], body["done"]) == ("buy milk", False)
    assert body["created_at"].startswith("2026-01-01T00:00:00")


def test_list_is_empty_then_newest_first(client: TestClient) -> None:
    assert client.get(BASE).json() == []
    for title in ("one", "two"):
        client.post(BASE, json={"title": title})
    assert [i["title"] for i in client.get(BASE).json()] == ["two", "one"]


def test_get_patch_delete_round_trip(client: TestClient) -> None:
    item_id = client.post(BASE, json={"title": "task"}).json()["id"]

    assert client.get(f"{BASE}/{item_id}").json()["title"] == "task"

    patched = client.patch(f"{BASE}/{item_id}", json={"done": True})
    assert patched.status_code == 200
    assert (patched.json()["title"], patched.json()["done"]) == ("task", True)

    deleted = client.delete(f"{BASE}/{item_id}")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(f"{BASE}/{item_id}").status_code == 404


def test_unknown_item_is_404_with_detail(client: TestClient) -> None:
    for response in (
        client.get(f"{BASE}/99"),
        client.patch(f"{BASE}/99", json={"done": True}),
        client.delete(f"{BASE}/99"),
    ):
        assert response.status_code == 404
        assert response.json() == {"detail": "Item 99 not found"}


def test_invalid_bodies_are_422(client: TestClient) -> None:
    assert client.post(BASE, json={}).status_code == 422
    assert client.post(BASE, json={"title": "   "}).status_code == 422
    assert client.post(BASE, json={"title": "x" * 201}).status_code == 422
    assert client.post(BASE, json={"title": "ok", "bogus": 1}).status_code == 422
    item_id = client.post(BASE, json={"title": "ok"}).json()["id"]
    assert client.patch(f"{BASE}/{item_id}", json={"title": ""}).status_code == 422
    assert client.patch(f"{BASE}/{item_id}", json={"done": "maybe"}).status_code == 422


def test_invalid_ids_are_422_not_500(client: TestClient) -> None:
    assert client.get(f"{BASE}/abc").status_code == 422
    assert client.get(f"{BASE}/0").status_code == 422
    assert client.get(f"{BASE}/{2**31}").status_code == 422
