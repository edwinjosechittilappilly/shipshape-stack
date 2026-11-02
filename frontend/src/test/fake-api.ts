import type { Item } from "../api/items";

export interface FakeResponse {
  status: number;
  body?: unknown;
}

/**
 * In-memory stand-in for the items API contract. Shared by the Vitest component tests (via a stubbed `fetch`)
 * and the Playwright `mocked` project (via `page.route`), so both layers exercise the same behaviour and can't drift.
 */
export class FakeItemsApi {
  private items: Item[];
  private nextId: number;

  constructor(seed: readonly Item[] = []) {
    this.items = seed.map((i) => ({ ...i }));
    this.nextId = Math.max(0, ...seed.map((i) => i.id)) + 1;
  }

  /** Newest first, like the real API. */
  list(): Item[] {
    return [...this.items].sort((a, b) => b.id - a.id);
  }

  handle(method: string, pathname: string, rawBody?: string | null): FakeResponse {
    const match = /^\/api\/v1\/items(?:\/(\d+))?$/.exec(pathname);
    if (!match) return { status: 404, body: { detail: "Not Found" } };
    const id = match[1] === undefined ? undefined : Number(match[1]);
    const body: unknown = rawBody ? JSON.parse(rawBody) : undefined;

    if (id === undefined) {
      if (method === "GET") return { status: 200, body: this.list() };
      if (method === "POST") return this.create(body);
      return { status: 405, body: { detail: "Method Not Allowed" } };
    }

    const index = this.items.findIndex((i) => i.id === id);
    const current = this.items[index];
    if (current === undefined) return { status: 404, body: { detail: "Item not found" } };
    if (method === "GET") return { status: 200, body: current };
    if (method === "DELETE") {
      this.items.splice(index, 1);
      return { status: 204 };
    }
    if (method === "PATCH") {
      const patch = (body ?? {}) as { title?: string; done?: boolean };
      const updated = { ...current, ...patch };
      this.items[index] = updated;
      return { status: 200, body: updated };
    }
    return { status: 405, body: { detail: "Method Not Allowed" } };
  }

  private create(body: unknown): FakeResponse {
    const title =
      typeof (body as { title?: unknown } | undefined)?.title === "string"
        ? (body as { title: string }).title.trim()
        : "";
    if (title.length < 1 || title.length > 200) {
      return { status: 422, body: { detail: [{ msg: "title must be 1..200 characters" }] } };
    }
    const item: Item = {
      id: this.nextId++,
      title,
      done: false,
      created_at: new Date().toISOString(),
    };
    this.items.push(item);
    return { status: 201, body: item };
  }
}
