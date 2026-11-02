import { expect, test } from "@playwright/test";
import { ItemsPage } from "./support/items-page";

// Runs against the real stack (E2E_BASE_URL, default http://localhost:8080) and a shared database, so every run uses
// a unique title, asserts only on its own row, and cleans up after itself even when an assertion fails.
test("creates, toggles and deletes an item end to end", async ({ page, request }) => {
  const title = `e2e ${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const items = new ItemsPage(page);

  try {
    await items.goto();

    await items.add(title);
    await expect(items.checkbox(title)).toBeVisible();
    await expect(items.checkbox(title)).not.toBeChecked();

    await items.checkbox(title).click(); // not .check(): state flips only after the server round trip
    await expect(items.checkbox(title)).toBeChecked();

    // The state must survive a reload, proving it reached the database rather than just React state.
    await page.reload();
    await expect(items.checkbox(title)).toBeChecked();

    await items.deleteButton(title).click();
    await expect(items.checkbox(title)).toHaveCount(0);
  } finally {
    const response = await request.get("/api/v1/items");
    if (response.ok()) {
      const leftovers = ((await response.json()) as { id: number; title: string }[]).filter(
        (item) => item.title === title,
      );
      for (const item of leftovers) await request.delete(`/api/v1/items/${String(item.id)}`);
    }
  }
});

test("serves the app shell and liveness endpoint", async ({ page, request }) => {
  const health = await request.get("/healthz");
  expect(health.ok()).toBe(true);

  await new ItemsPage(page).goto();
});
