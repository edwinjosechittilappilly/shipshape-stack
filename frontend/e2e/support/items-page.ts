import { expect, type Locator, type Page } from "@playwright/test";

/** Page object for the Items page. Locators use roles and labels only, mirroring how users (and screen readers) find things. */
export class ItemsPage {
  readonly heading: Locator;
  readonly list: Locator;
  readonly alert: Locator;
  readonly emptyState: Locator;

  constructor(private readonly page: Page) {
    this.heading = page.getByRole("heading", { name: "Items" });
    this.list = page.getByRole("list", { name: "Items" });
    this.alert = page.getByRole("alert");
    this.emptyState = page.getByText("No items yet");
  }

  async goto(): Promise<void> {
    await this.page.goto("/");
    await expect(this.heading).toBeVisible();
  }

  async add(title: string): Promise<void> {
    await this.page.getByRole("textbox", { name: "New item" }).fill(title);
    await this.page.getByRole("button", { name: "Add" }).click();
  }

  checkbox(title: string): Locator {
    return this.page.getByRole("checkbox", { name: title, exact: true });
  }

  deleteButton(title: string): Locator {
    return this.page.getByRole("button", { name: `Delete ${title}`, exact: true });
  }
}
