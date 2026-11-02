import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Item } from "../api/items";
import { FakeItemsApi } from "../test/fake-api";
import { ItemsPage } from "./ItemsPage";

const seed: Item[] = [
  { id: 1, title: "Buy milk", done: false, created_at: "2026-01-01T00:00:00Z" },
  { id: 2, title: "Walk dog", done: true, created_at: "2026-01-02T00:00:00Z" },
];

/** Routes `fetch` through the shared in-memory fake; `failWith` simulates an outage. */
function stubApi(api: FakeItemsApi, failWith?: Response) {
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof fetch>((input, init) => {
      if (failWith) return Promise.resolve(failWith.clone());
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
      const { status, body } = api.handle(init?.method ?? "GET", url, init?.body as string | null);
      return Promise.resolve(
        status === 204 ? new Response(null, { status }) : Response.json(body, { status }),
      );
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ItemsPage", () => {
  it("shows a loading state, then the items newest first", async () => {
    stubApi(new FakeItemsApi(seed));
    render(<ItemsPage />);

    expect(screen.getByRole("heading", { name: "Items" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Loading");

    const list = await screen.findByRole("list", { name: "Items" });
    const titles = within(list)
      .getAllByRole("checkbox")
      .map((box) => box.closest("label")?.textContent);
    expect(titles).toEqual(["Walk dog", "Buy milk"]);
    expect(screen.getByRole("checkbox", { name: "Walk dog" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Buy milk" })).not.toBeChecked();
  });

  it("shows the empty state", async () => {
    stubApi(new FakeItemsApi());
    render(<ItemsPage />);
    expect(await screen.findByText("No items yet")).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("adds an item, clears the input and puts it first", async () => {
    const user = userEvent.setup();
    stubApi(new FakeItemsApi(seed));
    render(<ItemsPage />);
    await screen.findByRole("list", { name: "Items" });

    await user.type(screen.getByRole("textbox", { name: "New item" }), "  Ship it  ");
    await user.click(screen.getByRole("button", { name: "Add" }));

    const first = (await screen.findAllByRole("checkbox"))[0];
    expect(first).toHaveAccessibleName("Ship it");
    expect(screen.getByRole("textbox", { name: "New item" })).toHaveValue("");
  });

  it("does not submit blank titles", async () => {
    const user = userEvent.setup();
    stubApi(new FakeItemsApi());
    render(<ItemsPage />);
    await screen.findByText("No items yet");

    await user.type(screen.getByRole("textbox", { name: "New item" }), "   ");
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
  });

  it("toggles done through the API", async () => {
    const user = userEvent.setup();
    const api = new FakeItemsApi(seed);
    stubApi(api);
    render(<ItemsPage />);

    const box = await screen.findByRole("checkbox", { name: "Buy milk" });
    await user.click(box);

    await vi.waitFor(() => {
      expect(screen.getByRole("checkbox", { name: "Buy milk" })).toBeChecked();
    });
    expect(api.list().find((i) => i.id === 1)?.done).toBe(true);
  });

  it("deletes an item", async () => {
    const user = userEvent.setup();
    stubApi(new FakeItemsApi(seed));
    render(<ItemsPage />);

    await user.click(await screen.findByRole("button", { name: "Delete Buy milk" }));

    await vi.waitFor(() => {
      expect(screen.queryByRole("checkbox", { name: "Buy milk" })).not.toBeInTheDocument();
    });
    expect(screen.getByRole("checkbox", { name: "Walk dog" })).toBeInTheDocument();
  });

  it("shows load failures in an alert and recovers on retry", async () => {
    const user = userEvent.setup();
    const api = new FakeItemsApi(seed);
    stubApi(api, Response.json({ detail: "Database unavailable" }, { status: 503 }));
    render(<ItemsPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Database unavailable");

    stubApi(api);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("list", { name: "Items" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows mutation failures in an alert and keeps the list", async () => {
    const user = userEvent.setup();
    const api = new FakeItemsApi(seed);
    stubApi(api);
    render(<ItemsPage />);
    await screen.findByRole("list", { name: "Items" });

    // Delete the row behind the UI's back so the next delete 404s.
    api.handle("DELETE", "/api/v1/items/1");
    await user.click(screen.getByRole("button", { name: "Delete Buy milk" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Item not found");
    expect(screen.getByRole("checkbox", { name: "Buy milk" })).toBeInTheDocument();
  });
});
