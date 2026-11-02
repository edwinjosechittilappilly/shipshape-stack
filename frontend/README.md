# Frontend

React 19 + TypeScript (strict) + Vite. A small Items page (list, add, toggle, delete) that talks to the backend through
relative `/api/v1/...` URLs, so the same build runs behind the Vite dev proxy, the nginx container, or an ingress.

Requires Node 24 (`nvm use`) and npm.

```bash
make setup               # npm ci
npm run dev              # http://localhost:5173, proxies /api to http://localhost:8000 (override: API_PROXY_TARGET)
make lint typecheck test # fast gate: ESLint + Prettier check, tsc, Vitest
make build               # dist/
make doctor              # React Doctor scan (see below)
```

## Layout

| Path                   | What                                                                  |
| ---------------------- | --------------------------------------------------------------------- |
| `src/api/items.ts`     | Typed API client (`ApiError`, `listItems`, `createItem`, ...)         |
| `src/components/`      | `ItemsPage` and its component tests                                   |
| `src/test/fake-api.ts` | In-memory API fake shared by Vitest and the mocked Playwright project |
| `e2e/`                 | Playwright specs: `*.mocked.spec.ts` and `*.fullstack.spec.ts`        |
| `nginx/`               | Container config template (`API_UPSTREAM`, `/healthz`, SPA fallback)  |

## React Doctor

[React Doctor](https://github.com/millionco/react-doctor) (pinned in `devDependencies`) scans for React-specific problems
ESLint does not cover (effects, state, performance, security, accessibility). `make doctor` runs
`react-doctor --yes --no-telemetry --blocking error .`: non-interactive, no score API / crash reporting, and a non-zero exit
only for error-severity findings. Fix findings rather than suppressing them; tune rules via `react-doctor rules` if a rule is
genuinely wrong for this project.

## End-to-end tests

```bash
make playwright-install      # once: downloads Chromium
make test-e2e                # `mocked` project: starts Vite, stubs /api with the fake. No backend needed. Includes axe a11y checks.
make test-e2e-fullstack      # `fullstack` project: real stack at E2E_BASE_URL (default http://localhost:8080), e.g. after `make up`
```

Specs use role/label locators and web-first assertions only. The full-stack spec uses a unique item title and cleans up
after itself, so it is safe against a shared database. Reports land in `playwright-report/`; traces are kept on first retry.

## Container

```bash
docker build -t app-frontend:local frontend
docker run --rm -p 8080:8080 -e API_UPSTREAM=http://host.docker.internal:8000 app-frontend:local
```

nginx-unprivileged (uid 101) serves the bundle on 8080, answers `GET /healthz` itself, proxies `/api/` to `API_UPSTREAM`
(default `http://backend:8000`), and falls back to `index.html` for client-side routes. It needs only `/tmp` and
`/etc/nginx/conf.d` writable, so it runs with a read-only root filesystem.

## Conventions

- ESLint 9 is pinned because `eslint-plugin-jsx-a11y` does not support ESLint 10 yet; TypeScript is held to the range typescript-eslint supports.
- Accessible names are part of the contract tests rely on: heading "Items", textbox "New item", button "Add", list "Items",
  checkbox named after the title, button "Delete &lt;title&gt;", errors in `role="alert"`.
