import { useEffect, useState, type SubmitEventHandler } from "react";
import { createItem, deleteItem, listItems, updateItem, type Item } from "../api/items";

type LoadState = "loading" | "ready" | "failed";

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}

export function ItemsPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [load, setLoad] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [adding, setAdding] = useState(false);
  const [attempt, setAttempt] = useState(0);

  // `attempt` is bumped by the Retry button to re-run the initial load.
  useEffect(() => {
    let cancelled = false;
    listItems()
      .then((loaded) => {
        if (cancelled) return;
        setItems(loaded);
        setError(null);
        setLoad("ready");
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(messageOf(e));
        setLoad("failed");
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const onRetry = () => {
    setLoad("loading");
    setError(null);
    setAttempt((n) => n + 1);
  };

  // Runs a mutation; any failure is surfaced in the single role="alert" region and leaves the list untouched.
  async function mutate(action: () => Promise<void>): Promise<void> {
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(messageOf(e));
    }
  }

  const onAdd: SubmitEventHandler<HTMLFormElement> = (event) => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    setAdding(true);
    void mutate(async () => {
      const created = await createItem(trimmed);
      setItems((current) => [created, ...current]);
      setTitle("");
    }).finally(() => {
      setAdding(false);
    });
  };

  const onToggle = (item: Item) =>
    mutate(async () => {
      const updated = await updateItem(item.id, { done: !item.done });
      setItems((current) => current.map((i) => (i.id === updated.id ? updated : i)));
    });

  const onDelete = (item: Item) =>
    mutate(async () => {
      await deleteItem(item.id);
      setItems((current) => current.filter((i) => i.id !== item.id));
    });

  return (
    <main>
      <h1>Items</h1>

      <form onSubmit={onAdd}>
        <label htmlFor="new-item">New item</label>
        <input
          id="new-item"
          type="text"
          value={title}
          maxLength={200}
          autoComplete="off"
          onChange={(e) => {
            setTitle(e.target.value);
          }}
        />
        <button type="submit" disabled={adding || !title.trim()}>
          Add
        </button>
      </form>

      {error && <p role="alert">{error}</p>}

      {load === "loading" && <p role="status">Loading…</p>}
      {load === "failed" && (
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      )}
      {load === "ready" && items.length === 0 && <p>No items yet</p>}
      {load === "ready" && items.length > 0 && (
        <ul aria-label="Items">
          {items.map((item) => (
            <li key={item.id}>
              <label className={item.done ? "done" : undefined}>
                <input type="checkbox" checked={item.done} onChange={() => void onToggle(item)} />
                {item.title}
              </label>
              <button
                type="button"
                aria-label={`Delete ${item.title}`}
                onClick={() => void onDelete(item)}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
