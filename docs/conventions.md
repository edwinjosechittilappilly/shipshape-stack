# Conventions

Rules that keep the codebase boring and predictable. Where a tool can enforce a rule, the tool is the rule; this document
explains the *why* and covers what tools cannot check. Proposals to change a convention go through a PR (and an
[ADR](adr/README.md) when it is a significant decision).

## Linting and formatting

| Language / file type | Formatter | Linter / checker | Why |
| --- | --- | --- | --- |
| Python (`backend/`) | `ruff format` | `ruff check`, `mypy --strict` | One fast tool for lint and format; strict types catch a whole class of bugs before tests do |
| TypeScript/React (`frontend/`) | Prettier | ESLint (flat config), `tsc --noEmit` (strict) | Prettier ends style debates; ESLint catches hooks and a11y mistakes; tsc is the type authority |
| Shell (`scripts/`, hooks) | n/a | shellcheck | Shell fails silently; shellcheck catches the common traps |
| GitHub workflows | n/a | actionlint | Catches expression and syntax errors that only fail at runtime |
| YAML | n/a | yamllint | Duplicate keys, indentation, truthy surprises |
| Markdown | n/a | markdownlint-cli2 | Consistent structure for docs agents also parse |
| Terraform/OpenTofu (`infra/`) | `tofu fmt` | `tofu validate`, Trivy config scan | Stay compatible with both tools |
| Helm (`deploy/`) | n/a | `helm lint --strict`, Trivy config scan | Render and security-check the manifests |
| Everything | `.editorconfig` | pre-commit hygiene hooks, gitleaks | Whitespace, line endings, secrets, large files |

Run `make format` to fix, `make lint` to check. Commit-time hooks (`uvx pre-commit install`) run the fast subset. Do not
disable a rule inline without a comment saying why; prefer fixing the code.

## Naming

- Python: `snake_case` functions and modules, `PascalCase` classes, `UPPER_SNAKE` constants. Pydantic models describe their
  role (`ItemCreate`, `ItemUpdate`, `ItemRead`); SQLAlchemy models are singular (`Item`).
- TypeScript: `camelCase` values, `PascalCase` components and types, one component per file named after it; hooks start with `use`.
- API: plural resource nouns in `kebab-case` paths (`/api/v1/items`), JSON fields `snake_case` (matching the backend; see `created_at`).
- Database: `snake_case`, plural table names, `id` primary keys, `created_at`/`updated_at` timestamps with time zone.
- Env vars: `UPPER_SNAKE`, no prefix games; one name per setting everywhere (code, compose, Helm, `.env.example`).
- Branches, commits, PR titles, labels: see [`CONTRIBUTING.md`](../CONTRIBUTING.md).
- Names say what, not how; avoid `Manager`, `Helper`, `utils` dumping grounds.

## Error handling

- Fail fast at the boundary: validate input with Pydantic and return `422`/`400`; never let bad data reach the database layer.
- Use specific exceptions; catch only what you can handle. No bare `except:` and no swallowing errors silently.
- The API returns errors as `{"detail": "..."}` with the correct status (`404` missing, `409` conflict, `422` invalid,
  `503` dependency down). Never leak stack traces, SQL, or internal hostnames to clients.
- Unexpected exceptions become `500`, are logged once with context at the boundary, and are not re-logged by every layer.
- The frontend shows failures in `role="alert"` regions, keeps the user's input, and never fails silently.
- Retries belong at one layer, are bounded, and apply only to idempotent operations.

## Logging

- Use the standard `logging` module (`logging.getLogger(__name__)`); `app/log_config.py` emits one JSON object per line to stdout and the level comes from `LOG_LEVEL`.
- Log events with key-value context (`item_id`, `request_id`), not interpolated prose; one log line per event.
- Never log secrets, tokens, full request bodies, or personal data. `DATABASE_URL` must be redacted if logged.
- `INFO` for lifecycle and business events, `WARNING` for recoverable surprises, `ERROR` for failed operations; no `print`.

## Configuration via environment

- Twelve-factor: config comes from environment variables, read in **one** settings module per service and passed in; never
  `os.environ[...]` scattered through the code.
- Every variable is documented in `.env.example` with a safe local default; production values live in Secrets, never in the repo.
- `APP_ENV` (`local|ci|staging|production`) may switch defaults but must not switch *behaviour* in ways tests cannot cover.
- The frontend has no runtime secrets: anything shipped to a browser is public. Environment-specific upstreams are handled by nginx (`API_UPSTREAM`).

## API versioning

- Public endpoints live under `/api/v1/`. Operational endpoints (`/healthz`, `/readyz`) are unversioned.
- Within a version, only make **backwards-compatible** changes: add optional fields, add endpoints. Removing or renaming
  fields, changing types, or tightening validation requires `/api/v2/` and a deprecation period.
- Breaking changes are marked with `!` in the PR title and the `breaking-change` label, and noted in the changelog.
- Responses are JSON objects or arrays of objects (never bare scalars), so fields can be added later.

## Database migrations

- Schema changes happen only through Alembic migrations, in the same PR as the code that needs them. Never edit a merged migration.
- **Expand/contract**: migrations must be compatible with the *previous* app release because the migration runs before pods roll
  over and rollbacks must work. Add nullable or defaulted columns first; backfill; start using; drop in a later release.
  Never rename or drop a column that running code still reads.
- Migrations are a separate deploy step (compose `migrate` service, Helm hook Job), never run at app start.
- Be explicit about locks: avoid table rewrites and non-concurrent index builds on large tables; set a lock timeout.
- Each migration is small, reversible where possible (`downgrade`), and tested by the integration suite, which applies migrations to a fresh database.
- Prefer database constraints (`NOT NULL`, `UNIQUE`, foreign keys, `CHECK`) to application-only validation.

## Dependency hygiene

- Add a dependency only when it earns its weight; justify it in the PR. Prefer the standard library and existing dependencies.
- Always commit the lockfile (`uv.lock`, `package-lock.json`); installs in CI are frozen (`uv sync --locked`, `npm ci`).
- Pin GitHub Actions by full commit SHA with a version comment; pin base images (tag, ideally digest).
- Dependabot opens update PRs (label `dependencies`); review changelogs, let CI decide, and merge regularly so updates stay small.
- Remove unused dependencies when you stop using them. Licenses must be compatible with Apache-2.0.

## Comments and documentation

- Code says *what*; comments say *why*: constraints, trade-offs, links to issues or ADRs. Delete comments that restate the code.
- No commented-out code (git remembers). `TODO` only with an issue link: `TODO(#123): ...`.
- Public API behaviour is documented by the OpenAPI schema (typed models with descriptions), not duplicated in prose.
- Config files are teaching material: comment the reasoning for non-obvious settings.
- When behaviour or a command changes, update the docs in the same PR.

## Best-practice heuristics for reviewers and agents

A checklist to apply to every change. If one fails, comment or fix it.

### Scope and size

- [ ] The PR does one thing and matches the linked issue's acceptance criteria. Unrelated cleanups are separate PRs.
- [ ] It is small enough to review properly (prefer under ~400 changed lines; `size/XL` should be split).
- [ ] No speculative abstractions, flags, or "while I'm here" features. Delete dead code you made obsolete.

### Correctness and tests

- [ ] A test fails without the change and passes with it; failure paths are covered ([testing guide](testing.md)).
- [ ] Tests assert behaviour at a boundary, are deterministic, contain no sleeps, and do not test mocks.
- [ ] Verification in the PR is real output of commands that were run, not assertions.

### Security

- [ ] No secrets, tokens, or real credentials; inputs are validated; SQL goes through the ORM or bound parameters.
- [ ] Workflows use least-privilege `permissions`, SHA-pinned actions, and never interpolate untrusted input into scripts.
- [ ] Containers stay non-root and read-only; no new open ports or broader network access without justification.

### Operability

- [ ] New config is an env var with a documented default in `.env.example`, compose, and the Helm chart.
- [ ] Migrations are backwards compatible with the previous release and separate from app start.
- [ ] Errors are handled once, logged with context, and never swallow failures or leak internals.
- [ ] Health endpoints keep their meaning: `/healthz` has no dependencies, `/readyz` checks the database.

### Maintainability

- [ ] Names are clear; functions are small and typed; no duplicated logic that should be shared (and no sharing of coincidences).
- [ ] Docs, `.env.example`, the changelog, and the ADR or plan are updated with the behaviour they describe.
- [ ] The change is easy to revert: no mixed refactor and behaviour change, no irreversible data migration without a plan.

### Agents specifically

- [ ] Followed [`AGENTS.md`](../AGENTS.md) and the relevant skill; did not bypass hooks, CI, or branch protection.
- [ ] Reported only commands actually run; flagged uncertainty and decisions needing a human with `status: needs-human`.
