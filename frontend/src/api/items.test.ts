import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createItem, deleteItem, listItems, updateItem } from "./items";

const item = { id: 1, title: "Write docs", done: false, created_at: "2026-01-01T00:00:00Z" };

function stubFetch(response: Response | Error) {
  const fn = vi.fn<typeof fetch>(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("items api client", () => {
  it("lists items from the relative API path", async () => {
    const fetchMock = stubFetch(Response.json([item]));
    await expect(listItems()).resolves.toEqual([item]);
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/items", expect.anything());
  });

  it("creates an item with a JSON body", async () => {
    const fetchMock = stubFetch(Response.json(item, { status: 201 }));
    await expect(createItem("Write docs")).resolves.toEqual(item);
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/items");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ title: "Write docs" }));
    expect(init?.headers).toMatchObject({ "Content-Type": "application/json" });
  });

  it("patches an item by id", async () => {
    const fetchMock = stubFetch(Response.json({ ...item, done: true }));
    await expect(updateItem(1, { done: true })).resolves.toMatchObject({ done: true });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/items/1");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PATCH");
  });

  it("deletes an item and accepts 204", async () => {
    const fetchMock = stubFetch(new Response(null, { status: 204 }));
    await expect(deleteItem(1)).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("DELETE");
  });

  it("surfaces the backend's detail message", async () => {
    stubFetch(Response.json({ detail: "Item not found" }, { status: 404 }));
    await expect(deleteItem(9)).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "Item not found",
    });
  });

  it("falls back to a status message when the error body is not JSON", async () => {
    stubFetch(new Response("<html>bad gateway</html>", { status: 502 }));
    await expect(listItems()).rejects.toThrow("Request failed (502)");
  });

  it("reports network failures as ApiError with status 0", async () => {
    stubFetch(new TypeError("Failed to fetch"));
    const error = await listItems().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 0, message: "Could not reach the server" });
  });

  it("rejects payloads that do not match the Item shape", async () => {
    stubFetch(Response.json([{ id: "1" }]));
    await expect(listItems()).rejects.toThrow("Unexpected response from the server");
  });
});
