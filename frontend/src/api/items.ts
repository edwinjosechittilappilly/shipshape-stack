// Typed client for the items API. Every call uses a relative `/api/v1/...` URL so the same bundle works behind
// the Vite dev proxy, the nginx container, and Kubernetes ingress without rebuilding.

export interface Item {
  id: number;
  title: string;
  done: boolean;
  created_at: string;
}

export interface ItemPatch {
  title?: string;
  done?: boolean;
}

/** Thrown for any non-2xx response or unreadable payload. `status` is 0 when the request never completed. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const BASE = "/api/v1/items";

function isItem(value: unknown): value is Item {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.id === "number" &&
    typeof v.title === "string" &&
    typeof v.done === "boolean" &&
    typeof v.created_at === "string"
  );
}

/** The backend reports errors as `{"detail": "..."}` (a list for request-validation failures). */
async function errorMessage(res: Response): Promise<string> {
  const fallback = `Request failed (${String(res.status)})`;
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && res.status === 422) return "The request was not valid";
  } catch {
    // Body was empty or not JSON (e.g. a proxy error page); the status-based message is the best we have.
  }
  return fallback;
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
      },
    });
  } catch {
    throw new ApiError(0, "Could not reach the server");
  }
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return res;
}

async function readItem(res: Response): Promise<Item> {
  const body: unknown = await res.json();
  if (!isItem(body)) throw new ApiError(res.status, "Unexpected response from the server");
  return body;
}

export async function listItems(): Promise<Item[]> {
  const body: unknown = await (await request(BASE)).json();
  if (!Array.isArray(body) || !body.every(isItem)) {
    throw new ApiError(200, "Unexpected response from the server");
  }
  return body;
}

export async function createItem(title: string): Promise<Item> {
  return readItem(await request(BASE, { method: "POST", body: JSON.stringify({ title }) }));
}

export async function updateItem(id: number, patch: ItemPatch): Promise<Item> {
  return readItem(
    await request(`${BASE}/${String(id)}`, { method: "PATCH", body: JSON.stringify(patch) }),
  );
}

export async function deleteItem(id: number): Promise<void> {
  await request(`${BASE}/${String(id)}`, { method: "DELETE" });
}
