"""Full HTTP -> service -> SQL -> Postgres round trips. Behaviour at the boundary, not wiring."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

BASE = "/api/v1/items"


def test_readyz_is_ready_against_a_real_database(client: TestClient) -> None:
    response = client.get("/readyz")
    assert (response.status_code, response.json()) == (200, {"status": "ready"})


def test_crud_round_trip_persists_across_requests(client: TestClient) -> None:
    created = client.post(BASE, json={"title": "  ship it  "})
    assert created.status_code == 201
    item = created.json()
    assert (item["title"], item["done"]) == ("ship it", False)
    # created_at must be a real timezone-aware ISO-8601 timestamp from the database.
    assert datetime.fromisoformat(item["created_at"]).tzinfo is not None

    assert client.get(f"{BASE}/{item['id']}").json() == item

    patched = client.patch(f"{BASE}/{item['id']}", json={"done": True})
    assert patched.status_code == 200
    assert (patched.json()["title"], patched.json()["done"]) == ("ship it", True)
    # The update was committed, not just held in the session.
    assert client.get(f"{BASE}/{item['id']}").json()["done"] is True

    renamed = client.patch(f"{BASE}/{item['id']}", json={"title": "shipped"})
    assert (renamed.json()["title"], renamed.json()["done"]) == ("shipped", True)

    assert client.delete(f"{BASE}/{item['id']}").status_code == 204
    assert client.get(f"{BASE}/{item['id']}").status_code == 404
    assert client.get(BASE).json() == []


def test_list_is_newest_first(client: TestClient) -> None:
    for title in ("first", "second", "third"):
        assert client.post(BASE, json={"title": title}).status_code == 201
    items = client.get(BASE).json()
    assert [i["title"] for i in items] == ["third", "second", "first"]
    created = [datetime.fromisoformat(i["created_at"]) for i in items]
    assert created == sorted(created, reverse=True)


def test_ties_on_created_at_are_ordered_by_id(client: TestClient, engine: Engine) -> None:
    stamp = datetime(2026, 1, 1).astimezone()
    with engine.begin() as conn:
        for title in ("a", "b", "c"):
            conn.execute(
                text("INSERT INTO items (title, created_at) VALUES (:t, :c)"),
                {"t": title, "c": stamp},
            )
    assert [i["title"] for i in client.get(BASE).json()] == ["c", "b", "a"]


def test_unknown_ids_are_404_with_detail(client: TestClient) -> None:
    for response in (
        client.get(f"{BASE}/12345"),
        client.patch(f"{BASE}/12345", json={"done": True}),
        client.delete(f"{BASE}/12345"),
    ):
        assert response.status_code == 404
        assert response.json() == {"detail": "Item 12345 not found"}


def test_deleting_twice_is_404_the_second_time(client: TestClient) -> None:
    item_id = client.post(BASE, json={"title": "once"}).json()["id"]
    assert client.delete(f"{BASE}/{item_id}").status_code == 204
    assert client.delete(f"{BASE}/{item_id}").status_code == 404


def test_validation_errors_are_422_and_store_nothing(client: TestClient) -> None:
    for body in ({}, {"title": ""}, {"title": "   "}, {"title": "x" * 201}, {"title": 5}):
        assert client.post(BASE, json=body).status_code == 422, body
    assert client.get(BASE).json() == []


def test_title_length_boundary_is_accepted_by_the_database(client: TestClient) -> None:
    response = client.post(BASE, json={"title": "é" * 200})
    assert response.status_code == 201
    assert client.get(f"{BASE}/{response.json()['id']}").json()["title"] == "é" * 200


def test_out_of_range_ids_are_422_not_a_database_error(client: TestClient) -> None:
    assert client.get(f"{BASE}/{2**31}").status_code == 422
    assert client.get(f"{BASE}/9999999999999999999").status_code == 422


def test_ids_are_never_reused_after_delete(client: TestClient) -> None:
    first = client.post(BASE, json={"title": "a"}).json()["id"]
    client.delete(f"{BASE}/{first}")
    second = client.post(BASE, json={"title": "b"}).json()["id"]
    assert second > first


def test_created_at_is_server_assigned_and_recent(client: TestClient) -> None:
    created = datetime.fromisoformat(client.post(BASE, json={"title": "now"}).json()["created_at"])
    assert abs(datetime.now(created.tzinfo) - created) < timedelta(minutes=1)
