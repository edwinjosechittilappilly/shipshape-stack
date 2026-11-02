# Improvement playbook

How to turn an audit into a sequence of small, safe pull requests that raise the score as fast as possible, using
the best-practice template as the source of patterns. Read `rubric.md` for what each check means.

## 1. Principles

1. **One concern per PR, always mergeable.** Each PR leaves the default branch green and is reviewable in
   minutes (target under ~400 changed lines; lockfiles and generated files do not count). Never bundle tooling
   changes with behaviour changes.
2. **Adapt, do not copy.** The template is an example "items" app (Python + React). Copy the *pattern* and
   rewrite it for the target's languages, package manager, test runner and deployment model (section 5). A
   copied job that calls `make -C backend` in a Go repo is worse than no job.
3. **Highest gain first, but respect dependencies.** Sort by the report's `gain`, then fix prerequisites first: a
   gate job needs the jobs it aggregates; a coverage threshold needs a coverage run; SHA pinning needs the
   workflows to exist.
4. **Make failures visible before making them blocking.** Introduce new checks as non-blocking or ratcheted at
   the current level, then tighten. Never loosen or delete an existing check to get green.
5. **Measure after every PR.** Re-run the scanner, record the delta, and stop when the remaining items are
   judgement calls rather than gaps.

## 2. Order of attack

| Phase | Goal | Checks it moves | Typical effort |
| --- | --- | --- | --- |
| 0. Safety | Remove committed secrets; rotate them | `SEC-NO-SECRETS`, `SEC-ENV-IGNORED` | S (rotation is the real work) |
| 1. Foundation | Anyone can clone, run, test, and knows the rules | `DOC-*`, `DX-*`, `QUAL-EDITORCONFIG`, `QUAL-LOCKFILES`, `DOC-LICENSE` | S-M |
| 2. CI gate | Every PR is checked by one required status | `CI-EXISTS`, `CI-PR-TRIGGER`, `CI-LINT/TEST/BUILD`, `CI-GATE`, `CI-PERMISSIONS`, `CI-TIMEOUTS`, `CI-CONCURRENCY`, `CI-PINNED` | M |
| 3. Quality + tests | Local and CI agree; tests protect behaviour | `QUAL-*`, `TEST-*` | M-L |
| 4. Security | Scanners and update bots run by default | `SEC-*`, `CI-ACTIONLINT`, `CI-SCHEDULE` | S-M |
| 5. Hygiene + agent layer | PRs/issues are structured; agents have rules, skills, hooks, review | `HYG-*`, `AGT-*` | M |
| 6. Deployment | Hardened images and declared deployments | `CTN-*`, `CI-DEPLOY`, `CI-RELEASE`, `SEC-PROVENANCE` | M-L |

Why this order: phases 0-2 convert "unknown" into a trustworthy red/green signal. Everything after depends on that
signal (you cannot ratchet coverage or require a scanner without CI). The agent layer comes after CI because
instructions that say "run `make check`" are only credible once `make check` exists and CI enforces it. Deployment
last because it needs the most context and benefits from every earlier gate.

Exceptions: a committed secret goes first regardless of score. A repo with CI already green can jump straight
to the largest `gain` items.

## 3. PR slicing examples

Use conventional titles (`type(scope): subject`, lower-case, no trailing period). Each slice lists what to add or
adapt from the template, how to verify, and which checks should flip. Skip slices whose checks already pass.

### Example plan for a Python or Node service (adapt names to your stack)

| # | Title | Add / adapt from the template | Verify | Flips |
| ---: | --- | --- | --- | --- |
| 0 | `security: remove committed env file and rotate credentials` | Delete the file, add `.env`/`.env.*`/`!.env.example` to `.gitignore` (`.gitignore`), add `.env.example` | `git ls-files \| grep -E '(^\|/)\.env$'` empty; credentials rotated (state who did it in the PR) | `SEC-NO-SECRETS`, `SEC-ENV-IGNORED`, `DX-ENV-EXAMPLE` |
| 1 | `docs: add license, contributing guide and quickstart` | `LICENSE`, `CONTRIBUTING.md`, README Quickstart/Testing sections, `CODE_OF_CONDUCT.md`, `SECURITY.md` | Follow the README on a clean clone | `DOC-README*`, `DOC-LICENSE`, `DOC-CONTRIB`, `DOC-COC`, `SEC-POLICY` |
| 2 | `build: add task runner with standard targets` | `Makefile` (setup, lint, format, typecheck, test, build, check) rewritten for your commands; `.editorconfig`; toolchain version files (`.python-version`, `.nvmrc`); `.gitattributes` | `make help`; `make check` locally | `DX-TASKRUNNER`, `DX-TOOLCHAIN`, `QUAL-EDITORCONFIG`, `DX-GITATTRIBUTES` |
| 3 | `ci: add pull request workflow with aggregate gate` | `.github/workflows/ci.yml` reduced to your jobs: `permissions: {}` + per-job read, `timeout-minutes`, `concurrency`, `persist-credentials: false`, `ci-success` aggregate (`needs`, `if: always()`) | Open the PR and watch it; run `actionlint`; then set branch protection to require only `ci-success` | `CI-EXISTS`, `CI-PR-TRIGGER`, `CI-LINT/TEST/BUILD`, `CI-GATE`, `CI-PERMISSIONS`, `CI-TIMEOUTS`, `CI-CONCURRENCY`, `SEC-CHECKOUT` |
| 4 | `ci: pin actions to commit SHAs and add dependabot` | Resolve each tag: `gh api repos/OWNER/REPO/commits/TAG --jq .sha`; `.github/dependabot.yml` with one entry per ecosystem plus `github-actions` and `docker` | Workflow still green; Dependabot appears under Insights | `CI-PINNED`, `SEC-DEPBOT` |
| 5 | `chore: add pre-commit hooks and secret scanning` | `.pre-commit-config.yaml` (whitespace, YAML, formatter, `gitleaks`), `.gitleaks.toml`; run hooks in CI (`hygiene` job) | `pre-commit run --all-files` clean | `QUAL-PRECOMMIT`, `SEC-SECRETS`, `QUAL-LINT/FORMAT` (if wired) |
| 6 | `build: configure linter, formatter and type checker` | Tool config (ruff/mypy, eslint/prettier/tsc, golangci-lint, clippy ...) adapted from `backend/pyproject.toml`, `frontend/eslint.config.js`; start non-strict if needed, then ratchet | `make lint typecheck` | `QUAL-LINT`, `QUAL-FORMAT`, `QUAL-TYPES`, `QUAL-STRICT` |
| 7 | `test: add unit tests for core logic and coverage floor` | Tests following `docs/testing.md`; coverage config with `fail_under` set to the **current** value | `make test` and coverage report | `TEST-UNIT`, `TEST-ASSERT`, `TEST-CONFIG`, `TEST-COVERAGE` |
| 8 | `test: add integration tests against a real database` | `tests/integration/`, compose DB service with healthcheck, CI service job | Job green in CI | `TEST-INTEGRATION`, `TEST-CI-SLOW`, `CTN-COMPOSE` |
| 9 | `ci: add security workflow (trivy, codeql)` | `.github/workflows/security.yml`, `.github/workflows/codeql.yml`, `trivy.yaml`, `.trivyignore` with dated justifications | Findings triaged, none silently ignored | `SEC-SCANNER`, `SEC-SAST`, `SEC-IAC-SCAN` |
| 10 | `chore: add issue forms, PR template, labels and labeler` | `.github/ISSUE_TEMPLATE/*.yml`, `pull_request_template.md`, `labels.yml` (+ sync workflow), `labeler.yml`, `release.yml`, `CODEOWNERS`, `scripts/ci/check_pr.py` adapted | Open a test PR; labels appear; title check works | `HYG-*`, `SEC-CODEOWNERS`, `AGT-ISSUE-TEMPLATE`, `AGT-LABELS` |
| 11 | `docs: add agent instructions, skills and hooks` | `AGENTS.md` (commands, repo map, conventions, boundaries, verification ladder), `CLAUDE.md` (`@AGENTS.md`), `.agents/skills/` (pull-request, code-review, ci-triage, tests), `.claude/settings.json`, hook scripts, `.coderabbit.yaml` | Fresh agent session can run `make check` from the file alone | `AGT-*` |
| 12 | `build: harden container images` | Multi-stage Dockerfile, pinned base (tag then digest), non-root `USER`, `.dockerignore`, healthcheck | `docker build` and `docker run` as non-root; Trivy clean | `CTN-DOCKERFILE`, `CTN-USER`, `CTN-NO-LATEST`, `CTN-DIGEST`, `CTN-MULTISTAGE`, `CTN-DOCKERIGNORE` |
| 13 | `feat(deploy): add helm chart with probes and security context` | `deploy/helm/app/` adapted; `values.schema.json`; kind smoke test script and CI job | `helm lint`, kind install passes | `CTN-DEPLOY-DESC`, `CTN-K8S-*`, `CTN-HELM-LINT`, `CI-DEPLOY` |
| 14 | `ci: add release workflow` | Tag-triggered build/publish/release notes; SBOM/provenance step | Dry-run on a pre-release tag | `CI-RELEASE`, `SEC-PROVENANCE`, `DOC-CHANGELOG` |

Combine adjacent tiny slices (for example 1 and 2) when the repo is small; split any slice that exceeds the size
budget. If the audit shows only a handful of failing checks, produce fewer PRs, not padded ones.

### Library or CLI (no deployables)

Skip slices 8, 12 and 13 (they will be `na` anyway). Replace them with: a **packaging/release** slice (build the
wheel/crate/jar/npm tarball in CI, publish on tag) and a **compatibility matrix** slice (test on the supported
language versions and OSes).

### Repos with CI already in place

Start from the report's top fixes. Typical high-gain, low-effort items there: add the aggregate gate, scope
`permissions`, pin actions, add `timeout-minutes`, add Dependabot, add secret scanning. Each is a one-file PR.

## 4. Writing a PR in the plan

Every planned PR in the plan document needs:

- **Title** in conventional form.
- **Goal** and the check ids it flips with the expected score delta (`+x.y`).
- **Files**: each file to add or change and the template file it is adapted from (link via `template_refs`).
- **Adaptation notes**: what differs for this stack.
- **Verification**: exact commands; for CI changes, "open the PR and link the green run".
- **Risk and rollback**: for example "branch protection must be updated after merge; revert restores the old required check".
- **Depends on**: earlier PRs.

## 5. Adapting template files to other stacks

| Template file | What to keep | What to change |
| --- | --- | --- |
| `.github/workflows/ci.yml` | Triggers, `concurrency`, `permissions: {}`, per-job `timeout-minutes`, `persist-credentials: false`, SHA pins, the `ci-success` aggregate with `if: always()`, path-filter `changes` job for monorepos | Replace job bodies with your toolchain. Python: `astral-sh/setup-uv` or `actions/setup-python` with `python-version-file`. Node: `actions/setup-node` with `node-version-file` and `cache: npm`. Go: `actions/setup-go` with `go-version-file: go.mod`, `golangci/golangci-lint-action`. Java: `actions/setup-java` with `cache: maven` (or `gradle`). Rust: `dtolnay/rust-toolchain` + `Swatinem/rust-cache`, `cargo fmt --check`, `cargo clippy -- -D warnings`. Ruby: `ruby/setup-ruby` with `bundler-cache`. .NET: `actions/setup-dotnet`, `dotnet format --verify-no-changes`. Keep the job *names* stable once branch protection depends on them (only `ci-success` should be required). |
| `Makefile` | Target names (`setup lint format typecheck test test-integration build check`), `lint` is check-only, `format` writes, `check` = lint + typecheck + test | Recipes. For a single-language repo drop per-package delegation. Use `just` or `Taskfile.yml` if the team prefers; keep the same verbs. |
| `.pre-commit-config.yaml` | Generic hooks, secret scan, workflow lint | Swap language hooks (ruff -> golangci-lint, rustfmt, rubocop, spotless ...); drop hooks for languages you do not have; keep it fast (< 10 s). |
| `.github/dependabot.yml` | Weekly schedule, grouping of minor/patch updates, ecosystems for actions and Docker | One `package-ecosystem` per manifest directory: `pip`/`uv`, `npm`, `gomod`, `cargo`, `maven`/`gradle`, `bundler`, `composer`, `nuget`, `terraform`, `helm`. Or use a Renovate config if that is your platform. |
| `backend/Dockerfile` | Multi-stage, pinned base, non-root numeric `USER`, only runtime files in the final stage, no secrets in layers | Builder image and install commands per language (Go: `CGO_ENABLED=0` build then `distroless/static:nonroot`; Java: JRE-only runtime image; Node: `npm ci --omit=dev`; Rust: `cargo build --release` then a minimal base). |
| `deploy/helm/app/` | `securityContext`, probes, resources, NetworkPolicy, PDB, values schema, migration hook | Ports, probe paths, env wiring, ingress. Remove the dev-only Secret template and bring your own secret management. If you do not deploy to Kubernetes, replace with your platform's descriptor (and expect `CTN-K8S-*` to become `na`). |
| `.github/workflows/security.yml`, `trivy.yaml` | Scan fs + image + config, severity gate, dated ignore file, scheduled run | Image names and scan paths. Language-native audit tools (`pip-audit`, `npm audit`, `cargo audit`, `govulncheck`) are fine additions or substitutes. |
| `AGENTS.md` | Section layout: commands, repo map, conventions, verification ladder, boundaries, PR rules | Everything concrete. Every command must be one you ran. Keep it under ~150 lines; move depth to `docs/`. |
| `.agents/skills/*` | Skill structure (frontmatter `name` = directory, "Use when ..." description) | Skill content: replace commands, paths and domain examples. Delete skills for workflows you do not have (e.g. `playwright-tests` without a UI). |
| `.claude/settings.json`, `scripts/agent-hooks/` | Deny-list for secrets, allow-list for read-only git and `make`, guard/format/stop hooks | Allow-list entries for your toolchain; formatter command in the format hook; the fast check run by the stop gate. |
| `.github/pull_request_template.md`, `scripts/ci/check_pr.py`, `labels.yml`, `labeler.yml` | Headings, title regex, label taxonomy | Area labels and path globs to match your directories; required headings if you rename sections (keep script and template in sync). |

### What not to copy

- The example items app, its migrations and e2e tests (copy the *structure* only).
- Frontend tooling (Playwright, React Doctor, a11y lint) into repos without a UI: the scanner marks it `na`, leave it that way.
- Kubernetes/Terraform content when you deploy elsewhere.
- Agent hooks you will not maintain: a stale hook that blocks legitimate commands costs more than it protects.
- Thresholds from the template (coverage, size labels) before measuring your baseline.

## 6. Getting template files

Preferred: a local checkout of the template (`git clone` or `gh repo clone <owner>/shipshape-stack /tmp/bpt`)
and copy files out of it. Without a clone, raw files work for public repos:
`curl -fsSL https://raw.githubusercontent.com/<owner>/shipshape-stack/main/<path> -o <path>`. If the template
repository is private, use `gh api repos/<owner>/shipshape-stack/contents/<path> --jq .content | base64 -d`
or a clone. Links in reports use `--template-url` (default points at the public location); override it for a fork.

## 7. Verification and the score delta

After each PR (on its branch, before merging):

```bash
python3 <skill-dir>/scripts/audit.py . --format json > /tmp/after.json
```

Record `score.overall`, the category deltas and which check ids changed status in the PR description:

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Overall | 62.3 | 71.8 | +9.5 |
| CI/CD | 31.0 | 86.0 | +55.0 |

Compare to the plan's prediction. A large mismatch means the check did not detect what you built (read its
`evidence`), or you built the wrong thing. Do not game the scanner: if a check passes without delivering the
underlying benefit, fix the implementation, not the evidence. Use `--min-score` in CI only after the repo is
comfortably above it, and prefer ratcheting it up one PR at a time.

## 8. Pitfalls

- **Renaming the required check.** Add the new aggregate job first, switch branch protection to it, then remove the old required checks.
- **SHA pinning needs the right SHA.** Resolve the commit of the *release tag* (annotated tags need dereferencing: `gh api repos/OWNER/REPO/git/ref/tags/TAG`), keep the version as a trailing `# vX.Y.Z` comment so Dependabot can bump it.
- **Coverage and type-strictness ratchets.** Set the threshold to today's value, not an aspirational one; strict type checking on a large untyped codebase belongs in its own staged PRs (per package or per module).
- **Secret scanners on history.** A first full-history scan is often noisy; baseline the known false positives in the scanner's allowlist, but rotate anything real that is already public.
- **Branch protection is a setting, not a file.** The scanner cannot see it; list it as a manual step in the PR that adds the gate.
- **Do not weaken checks.** If a new job is red on the default branch, fix or quarantine it with a linked issue and a deadline; never delete the check to get green.
