---
name: playwright-tests
description: "Use when writing, changing or debugging Playwright end-to-end tests in frontend/e2e: choosing locators, web-first assertions, the mocked vs fullstack projects, stubbing the network, unique test data, reading traces, accessibility checks. Also use to decide whether a behaviour needs e2e at all."
---

# Playwright tests

E2E tests check what only a real browser can: layout, focus, navigation, the UI and API working
together. They are the slowest, flakiest level, so each one must earn its place
(`docs/testing.md`: push checks down the pyramid whenever they can still fail for the right reason).

Read first: `frontend/playwright.config.ts`, `frontend/e2e/support/items-page.ts` (page object),
`frontend/e2e/support/mock-api.ts`, and one spec of each kind.

## Two projects

| | `mocked` (default) | `fullstack` |
| --- | --- | --- |
| Files | `e2e/*.mocked.spec.ts` | `e2e/*.fullstack.spec.ts` |
| Backend | none; `/api` stubbed with `page.route` (fake in `src/test/fake-api.ts`) | real compose stack at `E2E_BASE_URL` (default `http://localhost:8080`) |
| Starts | Vite via `webServer` | nothing - run `make up` first |
| Data | fully controlled, deterministic | shared DB: unique data, clean up |
| Use for | UI behaviour, error/empty states, a11y, keyboard flows | a few critical journeys proving UI <-> API <-> DB |

```bash
make -C frontend playwright-install     # once: downloads Chromium
make test-e2e                           # mocked; no backend needed
make test-e2e-fullstack                 # make up, then fullstack project
cd frontend && npx playwright test e2e/items.mocked.spec.ts -g "adds" --headed   # debug one test
cd frontend && npx playwright show-report                                         # after a failure
```

Default to **mocked**. Add a fullstack test only for a journey that breaks if the contract between
UI and API breaks (add, toggle, delete, survive reload). Keep fullstack to a handful.

## Locators: priority order

1. `getByRole('button', { name: 'Add' })` - what users and screen readers see (first choice)
2. `getByLabel('New item')` - form fields
3. `getByText('No items yet')` - static text; `getByPlaceholder`, `getByAltText` rarely
4. `getByTestId(...)` - only when nothing accessible exists. If you reach for it, first ask whether the UI is missing a label/role and fix that.
5. CSS / XPath - never (couples tests to markup).

Be strict: `exact: true` for names that prefix others (`Delete Buy milk` vs `Delete Buy milk now`);
scope with `list.getByRole('listitem')`; put locators in the page object (`ItemsPage`), assertions in the test.
Accessible names used here: heading "Items", textbox "New item", button "Add", list "Items", checkbox named after the title,
button "Delete <title>", empty text "No items yet", errors in `role="alert"`.

## Assertions: web-first, no sleeps

- `await expect(locator).toBeVisible() / toHaveText() / toBeChecked() / toHaveCount()` auto-retry until the timeout.
- **Never** `page.waitForTimeout`, fixed `sleep`, or `expect(await locator.isVisible()).toBe(true)` (no retry).
- Wait for a condition: `await expect(...)`, `page.waitForResponse(...)` for a specific call, `expect.poll(...)` for non-DOM state.
- Prefer `.click()` over `.check()` when state flips after a server round trip, then assert the new state.

Bad:

```ts
await page.click(".item:nth-child(2) button");
await page.waitForTimeout(1000);
expect(await page.locator(".done").count()).toBe(1);
```

Good:

```ts
await items.deleteButton("Walk dog").click();
await expect(items.checkbox("Walk dog")).toHaveCount(0);
```

## Network stubbing (mocked project)

- Use `mockApi(page, seed)`; it returns the fake so tests can seed/inspect server state.
- Match only backend calls: `page.route((url) => url.pathname.startsWith('/api/'), ...)` - a broad `**/api/**` glob swallows Vite's `/src/api` module requests.
- Failure paths: `route.fulfill({ status: 503, json: { detail: 'Database unavailable' } })` then assert `getByRole('alert')`.
- Register routes **before** `page.goto`. Assert on what the UI sends via the fake's state, not on request counts.
- Slow responses: delay in the route handler to assert loading states; never sleep in the test.

## Test data (fullstack)

The database is shared and non-empty. Each test:

1. creates uniquely named data: `` `e2e ${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}` ``
2. asserts only on its own rows (never `toHaveCount(1)` on the whole list)
3. cleans up in `finally` through the API (`request.delete`), so a failed assertion still cleans
4. proves persistence with `page.reload()` before asserting state

## Isolation and speed

Tests are independent and parallel (`fullyParallel`); no test depends on another, on order, or on
leftover state. No `test.only` (CI forbids it), no `test.skip` without a linked issue. One behaviour per test;
reuse the page object instead of copy-pasting steps.

## Accessibility

- Locating by role is already an a11y check: if you cannot find it by role/name, a user of assistive tech cannot either.
- `e2e/a11y.mocked.spec.ts` runs axe (`@axe-core/playwright`) on the empty, populated and error states. Extend it for new
  screens/states; the assertion is `violations` equals `[]`. Fix violations; do not exclude rules to pass.
- Verify keyboard flows (`await page.keyboard.press('Tab')`, Enter to submit) and focus after actions when relevant.

## Debugging failures

CI keeps traces (`on-first-retry`), screenshots and the HTML report as artifacts.

```bash
npx playwright show-trace path/to/trace.zip     # timeline, DOM snapshots, network, console
npx playwright test --ui                        # time-travel locally
npx playwright test --debug                     # inspector
```

Order of suspicion: wrong locator -> missing await/assertion -> race on a server round trip -> shared data (fullstack) -> real bug.
Reproduce locally with the same project before changing anything; do not raise timeouts or add retries as the fix.

## Checklist

- [ ] Could a unit test (Vitest + Testing Library) cover this cheaper? If yes, write that instead
- [ ] Mocked unless the test needs the real API
- [ ] Locators by role/label; no CSS; no `waitForTimeout`
- [ ] Unique data + cleanup for fullstack; failure and empty states covered for mocked
- [ ] Passes headed and headless, alone (`-g`) and in the full run; `--repeat-each=5` clean
- [ ] axe check added for any new screen or state
