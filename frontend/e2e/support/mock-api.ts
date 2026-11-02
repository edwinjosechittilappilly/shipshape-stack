import type { Page } from "@playwright/test";
import type { Item } from "../../src/api/items";
import { FakeItemsApi } from "../../src/test/fake-api";

/** True only for backend calls: a broad "any path containing /api/" glob would also swallow Vite's own /src/api module requests. */
export const isApiRequest = (url: URL): boolean => url.pathname.startsWith("/api/");

/**
 * Stubs every `/api/` request with the in-memory fake used by the unit tests, so the `mocked` project is deterministic
 * and needs no backend. Returns the fake so a test can inspect or seed server-side state.
 */
export async function mockApi(page: Page, seed: readonly Item[] = []): Promise<FakeItemsApi> {
  const api = new FakeItemsApi(seed);
  await page.route(isApiRequest, async (route) => {
    const request = route.request();
    const { status, body } = api.handle(
      request.method(),
      new URL(request.url()).pathname,
      request.postData(),
    );
    await route.fulfill(
      body === undefined ? { status } : { status, contentType: "application/json", json: body },
    );
  });
  return api;
}
