import { expect, test } from "@playwright/test";
import { ItemsPage } from "./support/items-page";
import { isApiRequest, mockApi } from "./support/mock-api";

const seed = [
  { id: 1, title: "Buy milk", done: false, created_at: "2026-01-01T00:00:00Z" },
  { id: 2, title: "Walk dog", done: true, created_at: "2026-01-02T00:00:00Z" },
];

test("shows the empty state when there are no items", async ({ page }) => {
  await mockApi(page);
  const items = new ItemsPage(page);
  await items.goto();

  await expect(items.emptyState).toBeVisible();
  await expect(items.list).toHaveCount(0);
});

test("lists existing items newest first with their done state", async ({ page }) => {
  await mockApi(page, seed);
  const items = new ItemsPage(page);
  await items.goto();

  await expect(items.list.getByRole("listitem")).toHaveText([/^Walk dog/, /^Buy milk/]);
  await expect(items.checkbox("Walk dog")).toBeChecked();
  await expect(items.checkbox("Buy milk")).not.toBeChecked();
});

test("adds, toggles and deletes an item", async ({ page }) => {
  const api = await mockApi(page);
  const items = new ItemsPage(page);
  await items.goto();

  await items.add("Write tests");
  await expect(items.checkbox("Write tests")).not.toBeChecked();
  await expect(page.getByRole("textbox", { name: "New item" })).toBeEmpty();
  await expect(items.emptyState).toBeHidden();

  await items.checkbox("Write tests").click(); // not .check(): state flips only after the server round trip
  await expect(items.checkbox("Write tests")).toBeChecked();
  expect(api.list()[0]?.done).toBe(true);

  await items.deleteButton("Write tests").click();
  await expect(items.emptyState).toBeVisible();
  expect(api.list()).toHaveLength(0);
});

test("shows an alert when loading fails", async ({ page }) => {
  await page.route(isApiRequest, (route) =>
    route.fulfill({ status: 503, json: { detail: "Database unavailable" } }),
  );
  const items = new ItemsPage(page);
  await items.goto();

  await expect(items.alert).toHaveText("Database unavailable");
  await expect(items.emptyState).toBeHidden();
});

test("shows an alert when adding fails and keeps the typed title", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/v1/items", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 500, json: { detail: "Could not save the item" } })
      : route.fallback(),
  );
  const items = new ItemsPage(page);
  await items.goto();

  await items.add("Will fail");
  await expect(items.alert).toHaveText("Could not save the item");
  await expect(page.getByRole("textbox", { name: "New item" })).toHaveValue("Will fail");
});
