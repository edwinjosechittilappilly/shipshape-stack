import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { ItemsPage } from "./support/items-page";
import { mockApi } from "./support/mock-api";

// A cheap smoke check, not a full audit: axe catches missing labels, bad contrast, landmark and ARIA mistakes.
test("empty page has no detectable accessibility violations", async ({ page }) => {
  await mockApi(page);
  const items = new ItemsPage(page);
  await items.goto();
  await expect(items.emptyState).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("populated page and error state have no detectable accessibility violations", async ({
  page,
}) => {
  await mockApi(page, [
    { id: 1, title: "Buy milk", done: true, created_at: "2026-01-01T00:00:00Z" },
    { id: 2, title: "Walk dog", done: false, created_at: "2026-01-02T00:00:00Z" },
  ]);
  const items = new ItemsPage(page);
  await items.goto();
  await expect(items.list).toBeVisible();

  // Trigger the alert by deleting a row that no longer exists server-side.
  await page.route("**/api/v1/items/2", (route) =>
    route.fulfill({ status: 404, json: { detail: "Item not found" } }),
  );
  await items.deleteButton("Walk dog").click();
  await expect(items.alert).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
