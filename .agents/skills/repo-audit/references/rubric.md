# repo-audit rubric

Everything the scanner scores, why, how it is detected and how to fix it. The scanner is static (filesystem
only: no network, no code execution), so it measures whether the *machinery* of good practice is present and
wired up. Section 3 lists what only a human or agent can judge, and how to adjust the score for it.

## 1. How scoring works

| Status | Points | Meaning |
| --- | ---: | --- |
| `pass` | 1.0 | Fully satisfied. |
| `partial` | 0.5 | Present but incomplete (e.g. config exists but CI never runs it). |
| `fail` | 0.0 | Missing or violated. |
| `na` | excluded | Not applicable to this repo; removed from numerator **and** denominator. |

- **Check score** = points. **Category score** = `100 * sum(weight_i * points_i) / sum(weight_i)` over applicable checks.
- **Overall score** = weighted mean of category scores using the category weights below, renormalised over
  categories that have at least one applicable check (so a repo without a UI is not penalised for the Frontend category).
- **Grade**: A >= 90, B >= 80, C >= 70, D >= 60, F below.
- **Gain** (the "impact" used for ranking fixes) is how many overall points the repo would gain if that check
  went to `pass`: `category_weight / total_applicable_category_weight * check_weight / category_applicable_weight * (1 - points) * 100`.
  Top fixes sort by gain (descending), then effort (S before M before L), then id. Effort hints: **S** = under an hour,
  mostly one file; **M** = a few hours, several files; **L** = days or needs a design decision.
- `--category X` scopes the whole run (score, grade, `--min-score`) to that category.

### Category weights (sum to 100) and rationale

| Category | Weight | Why this weight |
| --- | ---: | --- |
| CI/CD | 16 | CI is the gate every other practice is enforced through; a single trustworthy required check makes the rest reliable. |
| Testing | 14 | Tests are the executable definition of "works" and the main way agents verify their own changes. |
| Security & supply chain | 14 | Failures are costly (leaked secret, vulnerable image) and mostly preventable with configuration. |
| Agent readiness | 12 | The multiplier for AI-assisted work: instructions, skills, hooks, agent-shaped issues. |
| Code quality | 12 | Linters, formatters, types and lockfiles remove whole classes of review comments and make builds reproducible. |
| Documentation & onboarding | 10 | First-hour experience; table stakes, cheap to fix, not a safety property. |
| Containers & deployment | 8 | Hardened images and declared deployments; only applies when something is deployable. |
| PR & issue hygiene | 6 | Makes review and triage fast and automatable. |
| Developer experience | 4 | Few, quick checks (task runner, env template, pinned toolchains). |
| Frontend health | 4 | React/JS UI specifics; excluded entirely when no UI framework is detected. |

## 2. Stack detection and applicability

The scanner detects stacks from manifests (never by running anything) and marks checks that do not apply as `na`
instead of failing them.

| Stack | Detected by |
| --- | --- |
| python | `pyproject.toml`, `setup.py`, `setup.cfg`, `Pipfile`, `requirements*.txt`, or 5+ `.py` files |
| node / typescript | `package.json` with dependencies or JS/TS sources; TypeScript additionally via `tsconfig*.json`, a `typescript` dependency or `.ts` files |
| go, rust, jvm, ruby, php, dotnet | `go.mod`, `Cargo.toml`, `pom.xml`/`build.gradle*`, `Gemfile`, `composer.json`, `*.csproj`/`*.sln` |
| frontend | a UI framework dependency (react, vue, svelte, next, nuxt, @angular/core, solid-js, preact, lit, astro, remix, qwik) |
| react | react, react-dom, next, preact, remix or react-native dependencies (gates `FE-REACT-DOCTOR`) |
| service | frontend, a Dockerfile/compose file/Kubernetes workload, or a web-framework dependency (fastapi, flask, django, express, spring-boot, gin, axum, rails, laravel ...) |
| monorepo | two or more manifest directories |

Typical `na` rules: statically typed languages are excluded from `QUAL-TYPES`/`QUAL-STRICT`; Kubernetes checks need
workload manifests; Dockerfile checks need a Dockerfile; GitHub-Actions-specific CI checks are `na` when the repo
clearly uses another CI system (GitLab, CircleCI, Jenkins, ...) and has no GitHub workflows; libraries without
deployables skip the Containers category.

File listing: inside a git work tree the scanner audits `git ls-files --cached --others --exclude-standard`
(what would be committed, so ignored local files such as a gitignored `.env` are never flagged). Elsewhere, or with
`--no-git`, it walks the directory and skips `.git`, `node_modules`, virtualenvs, `vendor`, `dist`, `build`, `target`,
caches and nested worktrees.

"Reachable from CI": many repos run `make test` in CI and keep the real commands in the Makefile. For tool checks
(lint, tests, scanners) the scanner counts a command found in the task runner/scripts as run by CI when the CI config
calls `make`/`just`/`task`/`npm run`/`scripts/`. A tool present only in local config scores `partial`.

## 3. Qualitative pass (what the scanner cannot see)

The scanner proves a thing exists, not that it is good. After the scan, check these and **adjust with explicit
justification**: write adjustments as a table (`check id | scanner status | adjusted status | evidence you gathered`),
never silently change numbers, and keep the scanner score alongside the adjusted score in the report.

| Area | How to check | Adjust when |
| --- | --- | --- |
| README works | Follow it literally in a clean clone (or read it as a newcomer). Does it reach a running app and a green test run? Are prerequisites and versions stated? | `DOC-README-RUN` pass -> partial/fail if steps are missing, wrong or stale; fail -> partial if the instructions live in CONTRIBUTING. |
| Tests mean something | Read 3-5 tests from different areas. Do they assert behaviour (return values, state, HTTP responses, rendered output)? Are mocks hiding the behaviour under test? | `TEST-ASSERT`, `TEST-UNIT` down one step if tests mostly check "does not throw" or mock the unit itself; `TEST-INTEGRATION` down if the "integration" tests mock the database. |
| CI is green | `gh run list --branch <default> --limit 20` and `gh run view <id> --log-failed`. How often does the default branch fail? Are failures flaky reruns or real? Do runs take under ~15 minutes? | `CI-TEST`/`CI-LINT` pass -> partial if the default branch has been red for days or retries mask flakes. Never raise a score because CI is green. |
| Branch protection | `gh api repos/{owner}/{repo}/branches/<default>/protection` (needs admin) or ask. Is the aggregate check required, force-push blocked, review required? | `CI-GATE` pass -> partial when the gate job exists but is not a required check. |
| Docs are current | Sample 5 claims (commands, paths, env vars, versions) from README/AGENTS.md/docs and verify against the code. | `DOC-DOCS`, `AGT-INSTR-QUALITY`, `DOC-ARCH` down when several claims are false. |
| Agent instructions work | Start a fresh session with only the instruction files: can it find, run and test the code, and does it know the boundaries? | `AGT-INSTRUCTIONS`/`AGT-INSTR-QUALITY` down if the commands fail or contradict reality. |
| Repository settings | Secret scanning, push protection, Dependabot alerts, CodeQL default setup, required reviews (Settings > Security / Branches). | `SEC-SECRETS`, `SEC-SAST`, `SEC-DEPBOT` fail -> partial when the platform feature is enabled without config files. |
| Container reality | Do image builds work? Does the container start as non-root with a read-only root filesystem? | `CTN-USER` etc. down if the Dockerfile lies (e.g. `USER` set but files owned by root cause a crash). |

Adjustment protocol: (1) list every adjustment with evidence; (2) recompute the overall score by hand using
section 1 (or re-run with the evidence in mind: statuses in the JSON are inputs you can edit and recompute); (3) report
both numbers: "scanner 74.5% (C), adjusted 69.0% (D) after: ...". Adjustments must come from something you observed.

## 4. JSON output schema (`--format json`, `schema_version` 1)

```jsonc
{
  "schema_version": 1,
  "tool": "repo-audit",
  "scope": "all",                       // or comma-separated category ids when --category is used
  "repo": {
    "name": "my-repo", "path": "/abs/path",
    "stacks": ["python", "node", "typescript"],
    "flags": {"frontend": true, "react": true, "service": true, "monorepo": true, "github_actions": true, "other_ci": false},
    "files_scanned": 203, "listing": "git",   // "git" or "walk"
    "truncated": false                        // true when the 150k file cap was hit
  },
  "template_url": "https://github.com/<owner>/shipshape-stack/blob/main",
  "score": {
    "overall": 97.3, "grade": "A",
    "checks": {"total": 96, "applicable": 92, "pass": 89, "partial": 1, "fail": 2, "na": 4}
  },
  "categories": [
    {"id": "ci", "name": "CI/CD", "weight": 16, "applicable": true, "score": 100.0, "grade": "A", "rationale": "..."}
    // score and grade are null when the category is not applicable
  ],
  "checks": [
    {
      "id": "CI-PINNED", "category": "ci", "title": "Actions pinned to commit SHAs", "weight": 3, "effort": "S",
      "status": "pass",                 // pass | partial | fail | na
      "points": 1.0,                    // null when na
      "evidence": "12/12 action references pinned to a SHA",
      "remediation": "Pin each action to its commit SHA ...",
      "template_refs": [{"path": ".github/workflows/ci.yml", "url": "https://.../.github/workflows/ci.yml"}],
      "gain": 0.0    // overall points gained if this check passed (2 decimals)
    }
  ],
  "top_fixes": ["TEST-COVERAGE", "SEC-DEPBOT"],   // up to 10 check ids, best first
  "quick_wins": ["TEST-COVERAGE"],                // up to 8 effort-S check ids, best first
  "manual_review": ["README: follow it literally ...", "..."],
  "elapsed_seconds": 0.21
}
```

Exit codes: `0` success; `1` overall score below `--min-score`; `2` usage error (bad path, unknown category).
The schema only changes additively within a `schema_version`.

## 5. Known blind spots

- No YAML parser: workflows and manifests are read with line/regex heuristics. Unusual formatting can cause
  false positives or negatives; open the file when evidence looks wrong.
- Detection is per repository, not per package: one linter config anywhere satisfies the language's lint check.
- Platform settings (branch protection, repository security features, required reviews) are invisible: see section 3.
- Secret detection is shape-based (private-key blocks, `.env`, common token formats); it is not a substitute for a
  real scanner such as gitleaks. Findings are reported as paths only, never values.

## 6. Check catalogue

<!-- Generated prose contains literal globs such as *.test.* and __init__; lint the hand-written parts only. -->
<!-- markdownlint-disable MD037 MD049 MD050 -->
<!-- BEGIN GENERATED CHECKS (python3 scripts/audit.py --dump-rubric) -->

### Documentation & onboarding (weight 10)

*A newcomer's first hour decides whether they contribute. Cheap to fix, but it is table stakes rather than a safety property, so it is not weighted highest.*

#### `DOC-README` README with substance

Weight 3 · effort S · always applies

- **Why it matters (humans and agents):** First file humans and agents read. Without it nobody knows what the project is, who it is for, or where to start.
- **How it is detected:** README.* at repo root; pass at 25+ non-blank lines, partial for a stub.
- **How to fix:** Write a README: purpose, quickstart, layout, how to test, where docs/contributing live.
- **Template reference:** [`README.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/README.md)

#### `DOC-README-RUN` README shows how to install, run and test

Weight 3 · effort S · always applies

- **Why it matters (humans and agents):** A newcomer (or a fresh agent session) must go from clone to running tests using only the README.
- **How it is detected:** Fenced code blocks under setup/run/usage headings, plus a test command inside a code block.
- **How to fix:** Add Quickstart (prerequisites, one setup command, run command) and Testing sections with copy-pasteable commands.
- **Template reference:** [`README.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/README.md)

#### `DOC-LICENSE` License file

Weight 2 · effort S · always applies

- **Why it matters (humans and agents):** Without a license nobody (human or agent) may legally reuse or contribute to the code.
- **How it is detected:** LICENSE / LICENCE / COPYING at repo root.
- **How to fix:** Add a LICENSE file (choose one at choosealicense.com; Apache-2.0 or MIT are common).
- **Template reference:** [`LICENSE`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/LICENSE)

#### `DOC-CONTRIB` CONTRIBUTING guide

Weight 2 · effort S · always applies

- **Why it matters (humans and agents):** Defines the branch/commit/PR/test workflow so contributions and agent-authored PRs arrive in the shape reviewers expect.
- **How it is detected:** CONTRIBUTING.md at root, .github/ or docs/; pass at 30+ non-blank lines.
- **How to fix:** Document setup, branching, commit/PR conventions, the verification ladder and review expectations.
- **Template reference:** [`CONTRIBUTING.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/CONTRIBUTING.md)

#### `DOC-COC` Code of conduct

Weight 1 · effort S · always applies

- **Why it matters (humans and agents):** Sets behaviour expectations for community projects; required by most open-source platforms' community standards.
- **How it is detected:** CODE_OF_CONDUCT.md at root, .github/ or docs/.
- **How to fix:** Adopt the Contributor Covenant and add a reporting contact.
- **Template reference:** [`CODE_OF_CONDUCT.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/CODE_OF_CONDUCT.md)

#### `DOC-CHANGELOG` Changelog or release notes source

Weight 1 · effort S · always applies

- **Why it matters (humans and agents):** Lets users and agents see what changed between versions without reading every PR.
- **How it is detected:** CHANGELOG/HISTORY/NEWS at root or docs/; partial when only an automated tool (changesets, release-please) is configured.
- **How to fix:** Keep a CHANGELOG.md (Keep a Changelog format) or configure release notes generation.
- **Template reference:** [`CHANGELOG.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/CHANGELOG.md)

#### `DOC-DOCS` docs/ directory

Weight 2 · effort M · always applies

- **Why it matters (humans and agents):** Longer-lived knowledge (architecture, testing, deployment) does not fit in a README; agents load it on demand instead of guessing.
- **How it is detected:** docs/ (or doc/, documentation/, mkdocs.yml) with 3+ Markdown files passes; 1-2 partial.
- **How to fix:** Create docs/ with an index plus architecture, testing and deployment guides.
- **Template reference:** [`docs/README.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/docs/README.md), [`docs/architecture.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/docs/architecture.md), [`docs/testing.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/docs/testing.md)

#### `DOC-ARCH` Architecture overview

Weight 1 · effort S · always applies

- **Why it matters (humans and agents):** A one-page map of components, boundaries and data flow stops agents from inventing structure and speeds up human onboarding.
- **How it is detected:** ARCHITECTURE.md, docs/architecture*, docs/design*, docs/overview*.
- **How to fix:** Write docs/architecture.md: components, data flow, key decisions, where code lives.
- **Template reference:** [`docs/architecture.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/docs/architecture.md)

#### `DOC-ADR` Architecture decision records

Weight 1 · effort S · always applies

- **Why it matters (humans and agents):** Records why decisions were made, so they are not silently reversed by the next contributor or agent.
- **How it is detected:** docs/adr, docs/decisions, adr/ or doc/adr with Markdown records (2+ passes).
- **How to fix:** Adopt ADRs: add docs/adr/README.md, a template and one record per significant decision.
- **Template reference:** [`docs/adr/README.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/docs/adr/README.md), [`docs/adr/0000-template.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/docs/adr/0000-template.md)

#### `DOC-PLANS` Planning documents (plans/RFCs)

Weight 1 · effort S · always applies

- **Why it matters (humans and agents):** Written plans make work sliceable and reviewable before code exists, and give agents an executable spec.
- **How it is detected:** docs/plans, docs/rfcs, rfcs/, docs/design, docs/proposals or docs/specs with Markdown (2+ passes).
- **How to fix:** Add docs/plans/ with a TEMPLATE.md (goal, slices, acceptance, risks) and write plans for non-trivial work.
- **Template reference:** [`docs/plans/README.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/docs/plans/README.md), [`docs/plans/TEMPLATE.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/docs/plans/TEMPLATE.md)

#### `DOC-PKG-README` Each package has its own README

Weight 1 · effort S · N/A when: single-package repository

- **Why it matters (humans and agents):** In a monorepo an agent working in one package should not have to infer its commands from the root README.
- **How it is detected:** Every non-root manifest directory (package.json, pyproject.toml, go.mod, ...) contains a README.
- **How to fix:** Add a short README per package: purpose, commands (`make -C <pkg> ...`), layout.
- **Template reference:** [`backend/README.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/README.md), [`frontend/README.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/README.md)

### Agent readiness (weight 12)

*The multiplier for AI-assisted work: instructions, skills, hooks and agent-shaped issues turn an agent from a guesser into a contributor that follows your process.*

#### `AGT-INSTRUCTIONS` Agent instruction file (AGENTS.md)

Weight 4 · effort S · always applies

- **Why it matters (humans and agents):** The single most effective lever for agent output: build/test commands, conventions and boundaries loaded at session start.
- **How it is detected:** AGENTS.md at root passes; only vendor-specific files (CLAUDE.md, copilot-instructions, .cursorrules, GEMINI.md) is partial.
- **How to fix:** Write AGENTS.md (agent-agnostic): commands, repo map, conventions, verification ladder, hard boundaries.
- **Template reference:** [`AGENTS.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/AGENTS.md)

#### `AGT-INSTR-QUALITY` Instructions are actionable

Weight 3 · effort S · N/A when: no instruction file to assess

- **Why it matters (humans and agents):** Vague prose does not change agent behaviour; exact commands, boundaries and a definition of done do.
- **How it is detected:** Counts six signals in the instruction files: commands, conventions, repo map, hard boundaries, verification steps, PR/commit workflow. 5+ passes, 3+ partial; over 500 lines caps at partial.
- **How to fix:** Add the missing sections; keep the file short and link to docs/ for depth.
- **Template reference:** [`AGENTS.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/AGENTS.md)

#### `AGT-CLAUDE-BRIDGE` CLAUDE.md points at AGENTS.md

Weight 1 · effort S · N/A when: no AGENTS.md

- **Why it matters (humans and agents):** Claude Code reads CLAUDE.md, not AGENTS.md; without a bridge it silently ignores your agent rules.
- **How it is detected:** CLAUDE.md exists and is a symlink to, or references (`@AGENTS.md`), AGENTS.md. Only applies when AGENTS.md exists.
- **How to fix:** Create CLAUDE.md containing `@AGENTS.md` plus any Claude-specific notes (or symlink it).
- **Template reference:** [`CLAUDE.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/CLAUDE.md)

#### `AGT-SKILLS` Reusable agent skills

Weight 3 · effort M · always applies

- **Why it matters (humans and agents):** Skills package repeatable procedures (open a PR, write tests, triage CI) so agents follow your process instead of improvising.
- **How it is detected:** Directories with SKILL.md under .agents/skills, .claude/skills, .codex/skills, .cursor/skills. 3+ passes, 1-2 partial.
- **How to fix:** Add skills for your recurring workflows: pull-request, code-review, planning, ci-triage, tests.
- **Template reference:** [`.agents/skills/pull-request/SKILL.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.agents/skills/pull-request/SKILL.md), [`.agents/skills/code-review/SKILL.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.agents/skills/code-review/SKILL.md), [`.agents/skills/ci-triage/SKILL.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.agents/skills/ci-triage/SKILL.md)

#### `AGT-SKILLS-VALID` Skill files are well-formed

Weight 1 · effort S · N/A when: no skills

- **Why it matters (humans and agents):** A skill is only discovered if its frontmatter has a name and a description that says when to use it.
- **How it is detected:** Each SKILL.md starts with YAML frontmatter holding `name` (matching its directory) and a description of 40+ characters.
- **How to fix:** Fix frontmatter: `name: <dir-name>` and `description:` starting with 'Use when ...'.
- **Template reference:** [`.agents/skills/pull-request/SKILL.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.agents/skills/pull-request/SKILL.md)

#### `AGT-HOOKS` Agent hooks (guard, format, stop gate)

Weight 2 · effort M · always applies

- **Why it matters (humans and agents):** Hooks enforce rules deterministically (block destructive commands, format edits, gate 'done' on checks) where prose instructions are only advisory.
- **How it is detected:** Hook configs for Claude/Codex/Cursor/Gemini: 2+ configs or 2+ distinct events pass; one event is partial.
- **How to fix:** Add hooks that block destructive shell commands, auto-format edited files and run a fast check before the agent stops.
- **Template reference:** [`.claude/settings.json`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.claude/settings.json), [`.codex/hooks.json`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.codex/hooks.json), [`.cursor/hooks.json`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.cursor/hooks.json), [`scripts/agent-hooks/`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/scripts/agent-hooks/)

#### `AGT-PERMISSIONS` Agent permission allow/deny lists

Weight 2 · effort S · always applies

- **Why it matters (humans and agents):** Pre-approved safe commands remove prompt fatigue; a deny-list keeps secrets (.env, keys) out of the model's context.
- **How it is detected:** .claude/settings.json with `permissions`; pass when `deny` covers .env files, partial without it.
- **How to fix:** Add allow rules for make/test/read-only git+gh and deny rules for .env, *.pem, secrets/ and ssh keys.
- **Template reference:** [`.claude/settings.json`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.claude/settings.json)

#### `AGT-ISSUE-TEMPLATE` Agent-ready issue template

Weight 2 · effort S · always applies

- **Why it matters (humans and agents):** Agents execute well-specified tickets; a template forcing acceptance criteria, scope limits and verification turns issues into runnable tasks.
- **How it is detected:** Issue template containing acceptance criteria plus verification/out-of-scope/agent fields passes; acceptance criteria alone is partial.
- **How to fix:** Add an issue form (e.g. 'task') with Goal, Acceptance criteria, Out of scope, How to verify and an agent-ready checkbox.
- **Template reference:** [`.github/ISSUE_TEMPLATE/task.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/ISSUE_TEMPLATE/task.yml)

#### `AGT-REVIEW` Automated/agent code review configured

Weight 2 · effort M · always applies

- **Why it matters (humans and agents):** A second reviewer that follows your rules catches issues before a human looks; a review skill lets authors self-review the same way.
- **How it is detected:** Review-bot config (.coderabbit.yaml, greptile, bugbot, claude/copilot/codex review workflow) and a review skill. Both passes; either is partial.
- **How to fix:** Add .coderabbit.yaml (or equivalent) with path instructions and a code-review skill that mirrors your review rubric.
- **Template reference:** [`.coderabbit.yaml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.coderabbit.yaml), [`.agents/skills/code-review/SKILL.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.agents/skills/code-review/SKILL.md), [`.github/workflows/agent-review.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/agent-review.yml)

#### `AGT-DOCS` Agent workflow documentation

Weight 1 · effort S · always applies

- **Why it matters (humans and agents):** Explains how agents are expected to branch, verify, open PRs and hand off, so humans can supervise and improve the loop.
- **How it is detected:** docs/agents/, docs/agent*.md, docs/ai*.md or a dedicated agent-workflow section file.
- **How to fix:** Document the agent workflow: roles, labels, review flow, escalation (`status: needs-human`), what agents may never do.
- **Template reference:** [`docs/agents/`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/docs/agents/)

#### `AGT-COMMANDS` Custom agent commands

Weight 1 · effort S · always applies

- **Why it matters (humans and agents):** Slash commands/prompts turn the team's best prompts (plan, review, verify) into one keystroke.
- **How it is detected:** Files under .claude/commands, .cursor/commands, .codex/prompts or .agents/commands.
- **How to fix:** Add commands for plan, review and verify that invoke the matching skills.
- **Template reference:** [`.claude/commands/`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.claude/commands/)

#### `AGT-LABELS` Agent labels exist

Weight 1 · effort S · N/A when: no labels-as-code file

- **Why it matters (humans and agents):** Labels such as `agent: ready` and `status: needs-human` are the hand-off protocol between humans and agents.
- **How it is detected:** Labels-as-code file defines labels with 'agent' in their name. Only applies when a labels file exists.
- **How to fix:** Add `agent: ready`, `agent: in-progress`, `agent: authored`, `agent: review`, `status: needs-human` to labels.yml.
- **Template reference:** [`.github/labels.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/labels.yml)

### CI/CD (weight 16)

*CI is the objective gate that every other practice (tests, lint, security) is enforced through; without a trustworthy, single required check nothing else is reliable.*

#### `CI-EXISTS` CI is configured

Weight 4 · effort S · always applies

- **Why it matters (humans and agents):** Without automated checks every merge is a leap of faith, and agents get no signal that their change is safe.
- **How it is detected:** GitHub Actions workflows, GitLab CI, CircleCI, Jenkins, Azure Pipelines, Buildkite, Travis, Drone, etc.
- **How to fix:** Add .github/workflows/ci.yml running lint, typecheck, test and build on pull requests.
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml)

#### `CI-PR-TRIGGER` Checks run on pull requests

Weight 3 · effort S · N/A when: CI is not GitHub Actions

- **Why it matters (humans and agents):** Checks that only run after merge find problems too late; PR runs are the gate.
- **How it is detected:** A workflow triggered by pull_request or merge_group.
- **How to fix:** Add `on: pull_request` (and `merge_group` if you use a merge queue) to the main CI workflow.
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml)

#### `CI-LINT` CI runs lint/format/type checks

Weight 2 · effort S · always applies

- **Why it matters (humans and agents):** Style and type errors are cheapest to catch on every PR, mechanically, before a human reviews.
- **How it is detected:** Lint/format/typecheck commands (ruff, eslint, golangci-lint, clippy, mypy, tsc, make lint...) in CI text or in task-runner targets CI calls.
- **How to fix:** Add a lint job that calls the same `make lint typecheck` developers run locally.
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml), [`Makefile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/Makefile)

#### `CI-TEST` CI runs the tests

Weight 3 · effort S · always applies

- **Why it matters (humans and agents):** A red/green test signal on every PR is the foundation of safe automated change.
- **How it is detected:** Test commands (pytest, jest, vitest, go test, cargo test, mvn test, make test...) in CI text or in task-runner targets CI calls.
- **How to fix:** Add a test job calling `make test`; add integration/e2e jobs as they appear.
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml), [`Makefile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/Makefile)

#### `CI-BUILD` CI builds the artefact

Weight 1 · effort S · always applies

- **Why it matters (humans and agents):** Proves the code still compiles/bundles/containerises, not just that unit tests pass.
- **How it is detected:** Build commands (npm run build, go build, cargo build, docker build, mvn package, make build...) in CI or called task targets.
- **How to fix:** Add a build job (and a container image build if you ship one).
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml)

#### `CI-GATE` Single aggregate required check

Weight 3 · effort S · N/A when: CI is not GitHub Actions

- **Why it matters (humans and agents):** Branch protection should require ONE stable job; requiring individual jobs breaks as soon as path filters skip them or jobs are renamed.
- **How it is detected:** A PR-triggered workflow with a job named like success/gate/required that `needs:` 2+ jobs and runs `if: always()`. A workflow with a single job also passes.
- **How to fix:** Add a `ci-success` job with `needs: [all jobs]`, `if: always()` and a step failing on failure/cancelled results; require only it.
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml)

#### `CI-CONCURRENCY` Stale runs are cancelled

Weight 1 · effort S · N/A when: CI is not GitHub Actions

- **Why it matters (humans and agents):** Saves minutes and removes confusing results from superseded commits; essential when agents push often.
- **How it is detected:** The main PR workflow declares `concurrency:` with `cancel-in-progress`.
- **How to fix:** Add `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}` (never cancel runs on the default branch).
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml)

#### `CI-TIMEOUTS` Jobs have timeouts

Weight 2 · effort S · N/A when: CI is not GitHub Actions

- **Why it matters (humans and agents):** A hung job otherwise burns six hours of runner time and blocks the queue; a timeout turns hangs into fast, visible failures.
- **How it is detected:** Share of workflow jobs (excluding reusable-workflow calls) with `timeout-minutes`.
- **How to fix:** Add `timeout-minutes:` to every job (5-15 for most; longer only where justified).
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml)

#### `CI-PERMISSIONS` Least-privilege workflow permissions

Weight 3 · effort S · N/A when: CI is not GitHub Actions

- **Why it matters (humans and agents):** The default GITHUB_TOKEN can write to the repo; a compromised or prompt-injected step then inherits that power.
- **How it is detected:** Every workflow has a top-level `permissions:` block (not write-all) or sets it on every job.
- **How to fix:** Add `permissions: {}` at workflow level and grant `contents: read` (plus only what is needed) per job.
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml)

#### `CI-PINNED` Actions pinned to commit SHAs

Weight 3 · effort S · N/A when: CI is not GitHub Actions

- **Why it matters (humans and agents):** Tags are mutable: a hijacked action tag runs attacker code with your secrets. SHA pins (kept fresh by Dependabot) are immutable.
- **How it is detected:** Share of external `uses: owner/repo@ref` where ref is a 40-hex SHA (100% passes, 50%+ partial). Local and docker:// refs are ignored.
- **How to fix:** Pin each action to its commit SHA with the version as a trailing comment; let Dependabot bump them.
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml), [`.github/dependabot.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/dependabot.yml)

#### `CI-PATHS` Path filters in monorepo CI

Weight 1 · effort M · N/A when: single-package repository or non-GitHub CI

- **Why it matters (humans and agents):** Docs-only or single-package PRs should not pay for every package's pipeline; faster feedback keeps agents iterating.
- **How it is detected:** paths/paths-ignore on triggers or a changes-detection step (dorny/paths-filter, changed-files). Applies to repos with 2+ packages.
- **How to fix:** Add a `changes` job (dorny/paths-filter + .github/changes-filter.yml) and gate package jobs on it; keep the aggregate gate.
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml), [`.github/changes-filter.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/changes-filter.yml)

#### `CI-CACHE` Dependency caching

Weight 1 · effort S · always applies

- **Why it matters (humans and agents):** Caches cut CI time and reduce flaky downloads, which matters when many small agent PRs run CI.
- **How it is detected:** actions/cache, setup-* cache inputs, uv/rust cache, docker cache-from, GitLab cache:.
- **How to fix:** Enable the cache option on setup-node/setup-python/setup-uv or add actions/cache keyed on the lockfile.
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml)

#### `CI-RELEASE` Release workflow

Weight 2 · effort M · always applies

- **Why it matters (humans and agents):** Repeatable releases (tag -> build -> publish -> notes) remove manual steps and 'what version is deployed?' questions.
- **How it is detected:** Workflow triggered by tags/release events, or release tooling (release-please, semantic-release, goreleaser, changesets, publish steps).
- **How to fix:** Add a release workflow triggered on version tags that builds, publishes and creates release notes.
- **Template reference:** [`.github/release.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/release.yml), [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml)

#### `CI-DEPLOY` Deployment is automated or verified in CI

Weight 2 · effort L · N/A when: no deployable artefacts (Dockerfile, charts, IaC)

- **Why it matters (humans and agents):** Deploy steps that only exist in someone's shell history drift and break; a pipeline (or a cluster smoke test) keeps them honest.
- **How it is detected:** CI references helm/kubectl/terraform/cdk/fly/vercel/etc. deploys, kind/minikube smoke tests, or a deploy/cd workflow. Applies when containers or IaC exist.
- **How to fix:** Add a deploy workflow (environment + approvals) and a kind-based smoke test that installs the chart.
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml), [`scripts/kind-e2e.sh`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/scripts/kind-e2e.sh), [`docs/deployment.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/docs/deployment.md)

#### `CI-ACTIONLINT` Workflow files are linted

Weight 1 · effort S · N/A when: no GitHub workflows

- **Why it matters (humans and agents):** Workflow typos and unsafe expressions only fail at runtime; actionlint/zizmor catch them in seconds.
- **How it is detected:** actionlint, zizmor or check-github-workflows in CI or pre-commit.
- **How to fix:** Run actionlint in CI (pinned, checksum-verified) and in pre-commit.
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml), [`scripts/ci/install-tool.sh`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/scripts/ci/install-tool.sh)

#### `CI-SCHEDULE` Scheduled run catches drift

Weight 1 · effort S · N/A when: CI is not GitHub Actions

- **Why it matters (humans and agents):** New CVEs, deleted upstream tags and tool breakage appear without any commit; a weekly run surfaces them early.
- **How it is detected:** `schedule:` with a cron in any workflow.
- **How to fix:** Add a weekly cron trigger to CI (full run, including slow jobs).
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml)

### Code quality (weight 12)

*Linters, formatters, type checkers and lockfiles remove whole classes of review comments and make results reproducible.*

#### `QUAL-LINT` Linter configured per language

Weight 4 · effort S · N/A when: no supported language detected

- **Why it matters (humans and agents):** A linter encodes review feedback once, so humans stop repeating it and agents get immediate, local corrections.
- **How it is detected:** Per detected language: ruff/flake8/pylint, eslint/biome, golangci-lint/vet, clippy, checkstyle/spotbugs, rubocop, phpcs/phpstan, .NET analyzers.
- **How to fix:** Add the standard linter config for each language and a `make lint` (check-only) target.
- **Template reference:** [`backend/pyproject.toml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/pyproject.toml), [`frontend/eslint.config.js`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/eslint.config.js)

#### `QUAL-FORMAT` Formatter enforced per language

Weight 3 · effort S · N/A when: no supported language detected

- **Why it matters (humans and agents):** Automatic formatting ends style debates and keeps diffs (and agent edits) minimal.
- **How it is detected:** Per language: ruff format/black, prettier/biome, gofmt, rustfmt, spotless, rubocop, pint, dotnet format configured or run by tasks/CI.
- **How to fix:** Add the formatter, a `make format` (writes) target and a check-only variant inside `make lint`.
- **Template reference:** [`backend/pyproject.toml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/pyproject.toml), [`frontend/.prettierrc.json`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/.prettierrc.json)

#### `QUAL-TYPES` Static type checking

Weight 3 · effort M · N/A when: only statically typed languages detected

- **Why it matters (humans and agents):** Types turn whole classes of bugs into build failures and give agents precise feedback on interface mistakes.
- **How it is detected:** Python mypy/pyright config; TypeScript tsconfig plus a tsc step; Ruby sorbet/steep; PHP phpstan/psalm. Statically typed languages are excluded.
- **How to fix:** Add mypy (or pyright) / tsc --noEmit and wire them into `make typecheck` and CI.
- **Template reference:** [`backend/pyproject.toml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/pyproject.toml), [`frontend/tsconfig.json`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/tsconfig.json)

#### `QUAL-STRICT` Type checker runs in strict mode

Weight 2 · effort M · N/A when: no Python or TypeScript

- **Why it matters (humans and agents):** Non-strict checking lets `Any` and untyped defs hide the bugs types exist to catch.
- **How it is detected:** Python: mypy strict/disallow_untyped_defs or pyright strict. TypeScript: `"strict": true` in a tsconfig.
- **How to fix:** Enable `strict = true` (mypy) / `"strict": true` (tsconfig); fix or narrowly ignore the fallout.
- **Template reference:** [`backend/pyproject.toml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/pyproject.toml), [`frontend/tsconfig.json`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/tsconfig.json)

#### `QUAL-PRECOMMIT` Pre-commit hooks

Weight 2 · effort S · always applies

- **Why it matters (humans and agents):** Catches formatting, secrets and lint errors before they reach CI; the same hooks can run in CI so local and remote agree.
- **How it is detected:** .pre-commit-config.yaml (3+ hooks passes), lefthook.yml, or husky + lint-staged.
- **How to fix:** Add .pre-commit-config.yaml (whitespace, yaml/json checks, formatter, secret scan) and run it in CI.
- **Template reference:** [`.pre-commit-config.yaml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.pre-commit-config.yaml)

#### `QUAL-EDITORCONFIG` .editorconfig

Weight 1 · effort S · always applies

- **Why it matters (humans and agents):** Gives every editor (and agent edit tool) the same indentation and newline rules.
- **How it is detected:** .editorconfig at repo root.
- **How to fix:** Add .editorconfig with indent style/size, final newline and trailing-whitespace rules.
- **Template reference:** [`.editorconfig`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.editorconfig)

#### `QUAL-LOCKFILES` Dependency lockfiles committed

Weight 3 · effort S · N/A when: no lockable manifests

- **Why it matters (humans and agents):** Reproducible installs: the same versions locally, in CI and in the image; also required for meaningful vulnerability scanning.
- **How it is detected:** Per manifest directory: uv.lock/poetry.lock/pinned requirements, package-lock/yarn/pnpm lock, go.sum, Cargo.lock, Gemfile.lock, composer.lock, gradle.lockfile. Maven is excluded.
- **How to fix:** Generate and commit the lockfile (`uv lock`, `npm install --package-lock-only`, ...) and install with the frozen/`ci` variant in CI.
- **Template reference:** [`backend/uv.lock`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/uv.lock), [`frontend/package-lock.json`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/package-lock.json)

#### `QUAL-SHELLCHECK` Shell scripts are linted

Weight 1 · effort S · N/A when: no shell scripts

- **Why it matters (humans and agents):** Shell fails silently in surprising ways; shellcheck catches quoting and portability bugs in scripts agents and CI rely on.
- **How it is detected:** shellcheck/shfmt in CI, task targets or pre-commit. Applies when .sh files exist.
- **How to fix:** Run `shellcheck` over scripts/ in `make lint` (and a pre-commit hook).
- **Template reference:** [`Makefile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/Makefile), [`.pre-commit-config.yaml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.pre-commit-config.yaml)

### Testing (weight 14)

*Tests are the executable definition of correct behaviour and the main way agents verify their own work.*

#### `TEST-UNIT` Automated tests exist

Weight 5 · effort M · always applies

- **Why it matters (humans and agents):** Tests are the only objective definition of 'still works' for humans and agents alike; no tests means every change is unverified.
- **How it is detected:** Test files (test_*.py, *.test.ts, *_test.go, *Test.java, tests/, src/test ...) relative to source files: ratio >= 0.2 passes, >= 0.05 partial.
- **How to fix:** Add unit tests for core logic first (pure functions, services), then API-level tests; keep them fast and offline.
- **Template reference:** [`backend/tests/unit/`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/tests/unit/), [`frontend/src/components/ItemsPage.test.tsx`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/src/components/ItemsPage.test.tsx), [`docs/testing.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/docs/testing.md)

#### `TEST-ASSERT` Tests assert behaviour

Weight 3 · effort M · N/A when: no tests to inspect

- **Why it matters (humans and agents):** Tests without assertions (or mostly skipped) give false confidence: coverage numbers look fine while nothing is checked.
- **How it is detected:** Samples up to 80 test files: share containing assertions (90%+ passes), share of skipped/xfail tests (<10%), committed `.only`. This is a heuristic; review a few tests by hand.
- **How to fix:** Make each test assert an observable outcome (return value, HTTP response, persisted state); delete or fix skipped tests.
- **Template reference:** [`backend/tests/unit/test_item_service.py`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/tests/unit/test_item_service.py), [`docs/testing.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/docs/testing.md)

#### `TEST-INTEGRATION` Integration tests against real dependencies

Weight 3 · effort M · always applies

- **Why it matters (humans and agents):** Unit tests with mocks cannot catch schema, serialization and wiring bugs; integration tests against a real DB/service can.
- **How it is detected:** 2+ test files in integration/ directories or named *integration*/*IT; markers (pytest mark, testcontainers, build tags, `test-integration` target) alone are partial.
- **How to fix:** Add tests/integration/ that exercise the HTTP layer against a real database (compose or testcontainers) behind `make test-integration`.
- **Template reference:** [`backend/tests/integration/`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/tests/integration/), [`docs/testing.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/docs/testing.md)

#### `TEST-E2E` End-to-end tests

Weight 2 · effort M · N/A when: not a service/application

- **Why it matters (humans and agents):** Only e2e tests prove the assembled system (UI to DB) works; they guard the user journeys that matter most.
- **How it is detected:** Playwright/Cypress/WebdriverIO/Selenium config plus spec files, or e2e directories. Config or specs alone are partial. Applies to services/apps.
- **How to fix:** Add Playwright with a mocked-API project (fast, in CI) and a full-stack project against the compose stack.
- **Template reference:** [`frontend/playwright.config.ts`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/playwright.config.ts), [`frontend/e2e/`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/e2e/)

#### `TEST-CONFIG` Test runner configured and runnable by one command

Weight 1 · effort S · N/A when: no tests

- **Why it matters (humans and agents):** A single documented command with fixed settings (paths, markers, env) makes test runs identical everywhere.
- **How it is detected:** Python: pytest/unittest config; JS: real `test` script or jest/vitest config; compiled languages use their built-in runner.
- **How to fix:** Configure pytest/vitest in the package config and expose it as `make test`.
- **Template reference:** [`backend/pyproject.toml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/pyproject.toml), [`frontend/vite.config.ts`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/vite.config.ts)

#### `TEST-CI-SLOW` Integration/e2e tests run in CI

Weight 2 · effort M · N/A when: no integration/e2e tests

- **Why it matters (humans and agents):** Slow tests that only run on laptops rot; running them in CI keeps the expensive safety net alive.
- **How it is detected:** CI (or task targets it calls) invokes integration/e2e/playwright/cypress/testcontainers. Applies when such tests exist.
- **How to fix:** Add CI jobs for `make test-integration` (service container) and `make test-e2e`; gate them in the aggregate check.
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml)

#### `TEST-COVERAGE` Coverage measured with a threshold

Weight 2 · effort S · N/A when: no tests

- **Why it matters (humans and agents):** Coverage is a floor, not a goal: a threshold stops silent erosion, and the report shows agents which code is untested.
- **How it is detected:** coverage/pytest-cov/c8/nyc/jacoco/tarpaulin/codecov config; a fail-under/threshold setting passes, measurement alone is partial.
- **How to fix:** Enable coverage in the test target and set a fail-under ratchet (start at the current value).
- **Template reference:** [`backend/pyproject.toml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/pyproject.toml), [`frontend/vite.config.ts`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/vite.config.ts)

### Security & supply chain (weight 14)

*One leaked secret or vulnerable dependency outweighs many style wins; this category is weighted high because failures are costly and mostly preventable with config.*

#### `SEC-SCANNER` Vulnerability scanner in CI

Weight 3 · effort M · always applies

- **Why it matters (humans and agents):** Known-vulnerable dependencies and base images are the most common real-world exposure; scanning on every PR plus a schedule finds them early.
- **How it is detected:** trivy, grype, snyk, osv-scanner, npm/pip/cargo audit, govulncheck, dependency-review in CI or the task targets CI calls; config files alone are partial.
- **How to fix:** Add a security job running Trivy (fs + image + config) with a pinned version, severity gate and a documented ignore file.
- **Template reference:** [`.github/workflows/security.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/security.yml), [`trivy.yaml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/trivy.yaml), [`.trivyignore`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.trivyignore), [`scripts/security/trivy-scan.sh`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/scripts/security/trivy-scan.sh)

#### `SEC-SECRETS` Secret scanning

Weight 3 · effort S · always applies

- **Why it matters (humans and agents):** A leaked credential in git history is permanent; scanning before commit and in CI is the cheap prevention.
- **How it is detected:** gitleaks/trufflehog/detect-secrets etc. in CI, pre-commit, or a config file (.gitleaks.toml, .secrets.baseline). Two of the three signals pass, one is partial.
- **How to fix:** Add a gitleaks pre-commit hook and CI step plus a .gitleaks.toml allowlist for test fixtures.
- **Template reference:** [`.gitleaks.toml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.gitleaks.toml), [`.pre-commit-config.yaml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.pre-commit-config.yaml), [`.github/workflows/security.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/security.yml)

#### `SEC-DEPBOT` Automated dependency updates

Weight 3 · effort S · always applies

- **Why it matters (humans and agents):** Unpatched dependencies and stale action pins accumulate risk; bot PRs keep updates small, frequent and reviewable.
- **How it is detected:** dependabot.yml covering every detected ecosystem (plus docker and github-actions when used) or any Renovate config. Partial when ecosystems are missing.
- **How to fix:** Add .github/dependabot.yml with weekly updates and grouped minor/patch PRs for each ecosystem.
- **Template reference:** [`.github/dependabot.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/dependabot.yml)

#### `SEC-CODEOWNERS` CODEOWNERS

Weight 2 · effort S · always applies

- **Why it matters (humans and agents):** Routes reviews to the right people automatically and lets branch protection require owner approval on sensitive paths.
- **How it is detected:** CODEOWNERS at root, .github/ or docs/ with at least one rule.
- **How to fix:** Add .github/CODEOWNERS mapping paths (CI, infra, security) to teams.
- **Template reference:** [`.github/CODEOWNERS`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/CODEOWNERS)

#### `SEC-POLICY` SECURITY.md vulnerability policy

Weight 2 · effort S · always applies

- **Why it matters (humans and agents):** Tells reporters where to send findings privately and tells maintainers/agents never to file vulnerabilities as public issues.
- **How it is detected:** SECURITY.md at root, .github/ or docs/ mentioning how to report (advisory/email/private).
- **How to fix:** Add SECURITY.md: supported versions, private reporting channel, response expectations.
- **Template reference:** [`SECURITY.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/SECURITY.md)

#### `SEC-ENV-IGNORED` .env files are gitignored

Weight 2 · effort S · always applies

- **Why it matters (humans and agents):** The commonest secret leak is a committed .env; ignoring it by default removes the foot-gun (and keeps it out of agent context).
- **How it is detected:** .gitignore (any depth) has a rule for .env / .env.* / *.env.
- **How to fix:** Add `.env`, `.env.*` and `!.env.example` to .gitignore.
- **Template reference:** [`.gitignore`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.gitignore)

#### `SEC-NO-SECRETS` No committed secrets or private keys

Weight 4 · effort S · always applies

- **Why it matters (humans and agents):** Anything committed is public to every clone forever. This is the one finding that is an incident, not a todo.
- **How it is detected:** Static scan (no execution): committed .env/.env.local, private-key files and PEM blocks, cloud/Slack/GitHub/Stripe/Google token shapes, tfstate, .pypirc. .env.production/.staging only is partial. Paths are reported, never values.
- **How to fix:** Remove the file, ROTATE the credential, purge history if needed, add the pattern to .gitignore and enable secret scanning.
- **Template reference:** [`.gitignore`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.gitignore), [`.gitleaks.toml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.gitleaks.toml), [`.pre-commit-config.yaml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.pre-commit-config.yaml)

#### `SEC-SAST` Static application security testing (SAST)

Weight 2 · effort S · always applies

- **Why it matters (humans and agents):** Finds injection, deserialisation and crypto misuse in first-party code that dependency scanners cannot see.
- **How it is detected:** CodeQL, semgrep, bandit, gosec, brakeman, SonarCloud/Qube, Snyk Code in CI; config only is partial. Repository-level 'default setup' of CodeQL cannot be seen statically.
- **How to fix:** Add a codeql workflow (languages from your stack, weekly schedule) or semgrep with a pinned ruleset.
- **Template reference:** [`.github/workflows/codeql.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/codeql.yml)

#### `SEC-IAC-SCAN` Container/IaC misconfiguration scanning

Weight 1 · effort S · N/A when: no Dockerfile/Kubernetes/IaC files

- **Why it matters (humans and agents):** Privileged containers, missing limits and open ports are caught as misconfigurations before deploy.
- **How it is detected:** trivy config/fs, checkov, kube-linter, kubeconform, hadolint, tfsec, conftest, helm lint in CI or tasks. Applies when Docker/Kubernetes/Terraform files exist.
- **How to fix:** Run `trivy config`, hadolint and kubeconform (or checkov) on Dockerfiles, charts and IaC in CI.
- **Template reference:** [`.github/workflows/security.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/security.yml), [`scripts/security/trivy-scan.sh`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/scripts/security/trivy-scan.sh)

#### `SEC-CHECKOUT` Checkout does not persist credentials

Weight 1 · effort S · N/A when: no checkout steps

- **Why it matters (humans and agents):** `persist-credentials: false` stops later steps (or injected code) from reusing the token left in .git/config.
- **How it is detected:** Share of actions/checkout steps that set `persist-credentials: false`.
- **How to fix:** Add `with: {persist-credentials: false}` to every checkout that does not push.
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml)

#### `SEC-PRT` pull_request_target used safely

Weight 2 · effort S · N/A when: pull_request_target not used

- **Why it matters (humans and agents):** `pull_request_target` runs with write tokens and secrets; checking out the PR head there executes untrusted code with them.
- **How it is detected:** Flags workflows using pull_request_target that also check out the PR head (ref: github.event.pull_request.head.* / github.head_ref). Applies only when used.
- **How to fix:** Use `pull_request` for untrusted code; if target is required, never check out or run PR-controlled code in it.
- **Template reference:** [`.github/workflows/pr-labeler.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/pr-labeler.yml)

#### `SEC-PROVENANCE` SBOM / signing / provenance

Weight 1 · effort L · N/A when: no images or release workflow

- **Why it matters (humans and agents):** Lets consumers verify what was built from which commit and what is inside; increasingly required for enterprise adoption.
- **How it is detected:** syft/cyclonedx/spdx, cosign/sigstore, attest-build-provenance or SLSA generators in CI. Applies when images or a release workflow exist.
- **How to fix:** Generate an SBOM and attach build provenance (`actions/attest-build-provenance`) or sign images with cosign in the release job.
- **Template reference:** [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml)

### PR & issue hygiene (weight 6)

*Templates, labels and PR checks make the review/triage loop fast and automatable; important for agents, smaller direct risk.*

#### `HYG-PR-TEMPLATE` PR template with required sections

Weight 3 · effort S · always applies

- **Why it matters (humans and agents):** Forces every PR (including agent-authored ones) to state intent, changes and how it was verified; reviewers stop asking the same questions.
- **How it is detected:** pull_request_template.md with 3+ headings including a summary and verification/testing section.
- **How to fix:** Add .github/pull_request_template.md: Summary, Linked issue, Changes, Verification, Risk and rollback, Checklist.
- **Template reference:** [`.github/pull_request_template.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/pull_request_template.md)

#### `HYG-PR-CHECK` PR title/description validated in CI

Weight 2 · effort M · always applies

- **Why it matters (humans and agents):** Machine-checked conventions (Conventional Commit titles, required headings) make labels, changelogs and release notes automatable.
- **How it is detected:** CI references semantic-pull-request, commitlint, a check_pr script, danger or similar; a commitlint config alone is partial.
- **How to fix:** Add a pr-checks workflow that validates the title and required headings (adapt scripts/ci/check_pr.py).
- **Template reference:** [`.github/workflows/pr-checks.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/pr-checks.yml), [`scripts/ci/check_pr.py`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/scripts/ci/check_pr.py)

#### `HYG-ISSUE-FORMS` Issue forms

Weight 3 · effort S · always applies

- **Why it matters (humans and agents):** Structured forms produce complete bug reports and tasks; free-text issues cost a round of clarification each.
- **How it is detected:** .github/ISSUE_TEMPLATE/*.yml forms with `body:` (2+ passes); Markdown-only templates or one form is partial.
- **How to fix:** Add bug_report.yml, feature_request.yml and task.yml issue forms with required fields.
- **Template reference:** [`.github/ISSUE_TEMPLATE/bug_report.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/ISSUE_TEMPLATE/bug_report.yml)

#### `HYG-ISSUE-CONFIG` Issue chooser configured

Weight 1 · effort S · always applies

- **Why it matters (humans and agents):** Routes questions and security reports away from the issue tracker and blocks empty issues.
- **How it is detected:** .github/ISSUE_TEMPLATE/config.yml with blank_issues_enabled and/or contact_links.
- **How to fix:** Add config.yml: `blank_issues_enabled: false` and contact links (discussions, security policy).
- **Template reference:** [`.github/ISSUE_TEMPLATE/config.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/ISSUE_TEMPLATE/config.yml)

#### `HYG-LABELS-CODE` Labels defined as code

Weight 2 · effort S · always applies

- **Why it matters (humans and agents):** A versioned label taxonomy (type, area, size, status, agent) makes triage, automation and agent hand-offs reproducible.
- **How it is detected:** .github/labels.yml|json|toml; pass at 10+ labels, partial below.
- **How to fix:** Add .github/labels.yml and a sync workflow (labels-sync.yml).
- **Template reference:** [`.github/labels.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/labels.yml), [`.github/workflows/labels-sync.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/labels-sync.yml)

#### `HYG-LABELER` Automatic PR labeling

Weight 2 · effort M · always applies

- **Why it matters (humans and agents):** Auto-applied type/area/size labels let reviewers and automation filter work without manual bookkeeping.
- **How it is detected:** .github/labeler.yml plus a workflow using actions/labeler or a labeling script; either alone is partial.
- **How to fix:** Add labeler.yml path rules and a pr-labeler workflow (type from title, size from diff).
- **Template reference:** [`.github/labeler.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/labeler.yml), [`.github/workflows/pr-labeler.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/pr-labeler.yml), [`scripts/ci/pr_labels.py`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/scripts/ci/pr_labels.py)

#### `HYG-RELEASE-NOTES` Release notes categories configured

Weight 1 · effort S · always applies

- **Why it matters (humans and agents):** Categorised release notes are generated for free when PRs carry type labels.
- **How it is detected:** .github/release.yml, release-drafter, release-please, changesets, git-cliff or semantic-release config.
- **How to fix:** Add .github/release.yml mapping labels to changelog categories.
- **Template reference:** [`.github/release.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/release.yml)

### Containers & deployment (weight 8)

*Hardened images and declared deployments make 'works in CI' mean 'works in production'. Not applicable to libraries without deployables.*

#### `CTN-DOCKERFILE` Service is containerised

Weight 2 · effort M · N/A when: not a service/application

- **Why it matters (humans and agents):** A Dockerfile is the portable, reviewable definition of how the service runs; it is the unit CI, scanners and clusters work with.
- **How it is detected:** Dockerfile/Containerfile anywhere in the repo. Applies to services/applications.
- **How to fix:** Add a multi-stage Dockerfile per deployable (non-root, pinned base) and build it in CI.
- **Template reference:** [`backend/Dockerfile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/Dockerfile), [`frontend/Dockerfile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/Dockerfile)

#### `CTN-USER` Images run as a non-root user

Weight 4 · effort S · N/A when: no Dockerfile

- **Why it matters (humans and agents):** Root in the container turns any app compromise into a much easier node compromise; non-root is the single most valuable hardening step.
- **How it is detected:** Final build stage ends with a non-root USER (stage inheritance followed), or the base is a known non-root image (distroless:nonroot, *-unprivileged, chainguard).
- **How to fix:** Create a numeric user (`USER 10001:10001`) in the final stage and make files readable by it.
- **Template reference:** [`backend/Dockerfile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/Dockerfile), [`frontend/Dockerfile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/Dockerfile)

#### `CTN-NO-LATEST` Base images pinned (no :latest)

Weight 3 · effort S · N/A when: no Dockerfile

- **Why it matters (humans and agents):** `:latest` (or no tag) makes builds non-reproducible and lets a surprise upstream change break or compromise your image.
- **How it is detected:** Every external FROM has an explicit non-latest tag or digest. ARG-driven bases are skipped.
- **How to fix:** Pin `FROM image:1.2.3` (or `@sha256:`), and let Dependabot's docker ecosystem bump them.
- **Template reference:** [`backend/Dockerfile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/Dockerfile), [`frontend/Dockerfile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/Dockerfile), [`.github/dependabot.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/dependabot.yml)

#### `CTN-DIGEST` Base images pinned by digest

Weight 1 · effort M · N/A when: no external base images

- **Why it matters (humans and agents):** Tags can be re-pointed; digests are immutable. Combined with a bot that bumps them, this is fully reproducible and safe.
- **How it is detected:** Share of external FROM lines containing @sha256:.
- **How to fix:** Resolve each tag to a digest (`docker buildx imagetools inspect`) and write `image:tag@sha256:...`; let Dependabot update.
- **Template reference:** [`backend/Dockerfile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/Dockerfile), [`frontend/Dockerfile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/Dockerfile)

#### `CTN-MULTISTAGE` Multi-stage builds

Weight 1 · effort S · N/A when: no Dockerfile

- **Why it matters (humans and agents):** Keeps compilers, caches and dev dependencies out of the runtime image: smaller, faster to pull, smaller attack surface.
- **How it is detected:** Share of Dockerfiles with 2+ FROM stages.
- **How to fix:** Split into builder and runtime stages and COPY --from=builder only what runs.
- **Template reference:** [`backend/Dockerfile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/Dockerfile), [`frontend/Dockerfile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/Dockerfile)

#### `CTN-DOCKERIGNORE` .dockerignore present

Weight 2 · effort S · N/A when: no Dockerfile

- **Why it matters (humans and agents):** Without it the build context includes .git, node_modules and .env: slow builds, cache misses and leaked secrets in layers.
- **How it is detected:** A .dockerignore beside each Dockerfile or at the repo root.
- **How to fix:** Add .dockerignore excluding .git, .env*, node_modules, .venv, tests and docs.
- **Template reference:** [`backend/.dockerignore`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/.dockerignore), [`frontend/.dockerignore`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/.dockerignore)

#### `CTN-COMPOSE` Local stack via Compose

Weight 2 · effort S · N/A when: no Dockerfile

- **Why it matters (humans and agents):** `docker compose up` gives humans and agents a one-command, production-shaped environment (DB, migrations, app) for integration and e2e tests.
- **How it is detected:** docker-compose.yml / compose.yaml; healthchecks defined passes, bare file is partial.
- **How to fix:** Add docker-compose.yml with the DB (healthcheck), a migration service and the app services.
- **Template reference:** [`docker-compose.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/docker-compose.yml)

#### `CTN-DEPLOY-DESC` Deployment is described as code

Weight 3 · effort L · N/A when: not a service/application

- **Why it matters (humans and agents):** If the way to deploy lives only in someone's head, nobody (human or agent) can reproduce, review or roll it back.
- **How it is detected:** Helm chart, Kubernetes workload manifests, kustomize, Terraform/Pulumi/CDK/Bicep, or a platform descriptor (fly.toml, serverless.yml, vercel.json, ...). Applies to services.
- **How to fix:** Add a Helm chart (or platform descriptor) under deploy/ with values, schema and a hook Job for migrations.
- **Template reference:** [`deploy/helm/app/`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/deploy/helm/app/), [`docs/deployment.md`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/docs/deployment.md)

#### `CTN-K8S-PROBES` Kubernetes workloads define probes

Weight 2 · effort S · N/A when: no Kubernetes workloads

- **Why it matters (humans and agents):** Without liveness/readiness probes Kubernetes routes traffic to broken pods and never restarts hung ones.
- **How it is detected:** Workload manifests/Helm templates (and chart values) mention readinessProbe and livenessProbe/startupProbe.
- **How to fix:** Add readiness + liveness probes pointing at cheap /readyz and /healthz endpoints.
- **Template reference:** [`deploy/helm/app/templates/backend-deployment.yaml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/deploy/helm/app/templates/backend-deployment.yaml)

#### `CTN-K8S-RESOURCES` Kubernetes workloads set resource requests/limits

Weight 2 · effort S · N/A when: no Kubernetes workloads

- **Why it matters (humans and agents):** Unbounded pods starve neighbours and make scheduling and autoscaling unpredictable.
- **How it is detected:** `resources:` with requests/limits in manifests, templates or chart values.
- **How to fix:** Set conservative requests and memory limits in values.yaml and reference them from every container.
- **Template reference:** [`deploy/helm/app/values.yaml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/deploy/helm/app/values.yaml)

#### `CTN-K8S-SECCTX` Kubernetes security context hardened

Weight 3 · effort S · N/A when: no Kubernetes workloads

- **Why it matters (humans and agents):** runAsNonRoot, read-only root filesystem, no privilege escalation and dropped capabilities contain a compromised container.
- **How it is detected:** Per workload (and chart values): 3+ of runAsNonRoot, readOnlyRootFilesystem, allowPrivilegeEscalation: false, capabilities drop ALL, seccompProfile passes; any securityContext is partial.
- **How to fix:** Set the restricted pod-security profile fields in values.yaml and mount emptyDir for writable paths.
- **Template reference:** [`deploy/helm/app/values.yaml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/deploy/helm/app/values.yaml), [`deploy/helm/app/templates/backend-deployment.yaml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/deploy/helm/app/templates/backend-deployment.yaml)

#### `CTN-IAC` Infrastructure as code

Weight 1 · effort L · N/A when: not a service/application

- **Why it matters (humans and agents):** Reviewable, repeatable infrastructure beats console clicks; lockfiles pin provider versions.
- **How it is detected:** Terraform/OpenTofu, Pulumi, CDK, Bicep or similar; Terraform without a committed .terraform.lock.hcl is partial.
- **How to fix:** Describe the environment in Terraform/OpenTofu modules with committed lock files and a plan-in-CI job.
- **Template reference:** [`infra/terraform/`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/infra/terraform/)

#### `CTN-HELM-LINT` Helm charts are linted/validated in CI

Weight 1 · effort S · N/A when: no Helm charts

- **Why it matters (humans and agents):** Template errors and invalid manifests otherwise surface at deploy time.
- **How it is detected:** helm lint / helm template / kubeconform / chart-testing in CI or tasks. Applies when charts exist.
- **How to fix:** Add `make helm-lint` (helm lint + helm template | kubeconform) and run it in CI.
- **Template reference:** [`Makefile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/Makefile), [`.github/workflows/ci.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/ci.yml)

### Developer experience (weight 4)

*Task runner, env template and pinned toolchains make setup one command; small weight because the checks are few and quick to satisfy.*

#### `DX-TASKRUNNER` Task runner with standard targets

Weight 4 · effort S · always applies

- **Why it matters (humans and agents):** One discoverable entrypoint (`make help`) with the same verbs everywhere lets humans and agents run lint/test/build without reading CI YAML.
- **How it is detected:** Root Makefile/justfile/Taskfile/package.json scripts/mise: covers setup, lint, format, test, run/build groups (4+ passes, 2+ partial). Go/Rust/.NET repos relying on the bare toolchain are partial.
- **How to fix:** Add a root Makefile with setup, lint, format, typecheck, test, build and check targets that CI also calls.
- **Template reference:** [`Makefile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/Makefile), [`backend/Makefile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/Makefile), [`frontend/Makefile`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/Makefile)

#### `DX-ENV-EXAMPLE` .env.example documents configuration

Weight 3 · effort S · N/A when: not a service/application

- **Why it matters (humans and agents):** Documents every environment variable with a safe default so setup does not depend on tribal knowledge or real secrets.
- **How it is detected:** `.env.example` / `.env.sample` / `.env.template` (any depth). Applies to services.
- **How to fix:** Commit .env.example with every variable, safe local defaults and a comment on each; gitignore the real .env.
- **Template reference:** [`.env.example`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.env.example)

#### `DX-TOOLCHAIN` Toolchain versions pinned

Weight 3 · effort S · N/A when: no supported language detected

- **Why it matters (humans and agents):** 'Works on my machine' disappears and agents install the right runtime before running anything.
- **How it is detected:** Per detected language: .python-version, .nvmrc/.node-version, go directive, rust-toolchain, .java-version, .ruby-version, global.json or mise/.tool-versions. A version floor only is half credit.
- **How to fix:** Commit the version file for each runtime and use it from CI (`python-version-file`, `node-version-file`).
- **Template reference:** [`backend/.python-version`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/backend/.python-version), [`frontend/.nvmrc`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/.nvmrc)

#### `DX-GITIGNORE` .gitignore covers build artefacts

Weight 2 · effort S · always applies

- **Why it matters (humans and agents):** Keeps dependency folders, caches and local env files out of history and out of agent context.
- **How it is detected:** .gitignore mentions the standard artefacts for each detected stack (node_modules, __pycache__/.venv, target, bin/obj ...).
- **How to fix:** Start from the GitHub gitignore template for your stack and add .env, coverage and tool caches.
- **Template reference:** [`.gitignore`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.gitignore)

#### `DX-GITATTRIBUTES` Line endings normalised (.gitattributes)

Weight 1 · effort S · always applies

- **Why it matters (humans and agents):** Prevents CRLF/LF churn and broken shell scripts on Windows checkouts.
- **How it is detected:** .gitattributes with `text=auto` or `eol=lf`.
- **How to fix:** Add `* text=auto` and `*.sh text eol=lf` to .gitattributes.
- **Template reference:** [`.gitattributes`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.gitattributes)

### Frontend health (weight 4)

*React/JS UI specific tooling (React Doctor, a11y, Playwright, strict TS). Excluded entirely when no UI framework is detected.*

#### `FE-REACT-DOCTOR` React Doctor in scripts and CI

Weight 3 · effort S · N/A when: no React app detected

- **Why it matters (humans and agents):** Surfaces dead code, unsafe effects, a11y and perf pitfalls in React code with one command; cheap to gate in CI and easy for agents to act on.
- **How it is detected:** `react-doctor` in package scripts/dependencies, a config file, or CI. Both script/config and CI passes; one is partial. Applies to React/Next apps.
- **How to fix:** Add a `doctor` script (`npx react-doctor@latest .`), run it via a CI job (non-blocking at first), then ratchet.
- **Template reference:** [`.github/workflows/react-doctor.yml`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/.github/workflows/react-doctor.yml), [`frontend/package.json`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/package.json)

#### `FE-A11Y-LINT` Accessibility linting and tests

Weight 3 · effort S · N/A when: no JS UI framework detected

- **Why it matters (humans and agents):** Accessibility bugs are invisible to unit tests; lint rules plus automated axe checks catch the majority at PR time.
- **How it is detected:** eslint-plugin-jsx-a11y (or vue/svelte/angular equivalents) AND an axe integration (@axe-core/playwright, jest-axe, vitest-axe) passes; one is partial.
- **How to fix:** Add eslint-plugin-jsx-a11y to the ESLint config and an axe scan to the Playwright suite.
- **Template reference:** [`frontend/eslint.config.js`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/eslint.config.js), [`frontend/e2e/a11y.mocked.spec.ts`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/e2e/a11y.mocked.spec.ts)

#### `FE-PLAYWRIGHT` Browser e2e tests (Playwright)

Weight 2 · effort M · N/A when: no JS UI framework detected

- **Why it matters (humans and agents):** Real-browser tests protect the user journeys; Playwright's accessible-name selectors also force an accessible UI.
- **How it is detected:** @playwright/test with a playwright.config; Cypress or another browser runner is partial.
- **How to fix:** Add Playwright with `mocked` (stubbed API, CI-fast) and `fullstack` projects.
- **Template reference:** [`frontend/playwright.config.ts`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/playwright.config.ts), [`frontend/e2e/`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/e2e/)

#### `FE-TS-STRICT` TypeScript strict mode

Weight 3 · effort S · N/A when: no JS UI framework detected

- **Why it matters (humans and agents):** Strict TS catches null/undefined and implicit-any bugs at compile time and gives agents reliable type feedback across components.
- **How it is detected:** tsconfig with `"strict": true`; a tsconfig that only extends a shared base is partial; plain JS fails.
- **How to fix:** Migrate to TypeScript and enable strict; use `// @ts-expect-error` narrowly while migrating.
- **Template reference:** [`frontend/tsconfig.json`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/tsconfig.json)

#### `FE-COMPONENT-TESTS` Component tests with Testing Library

Weight 2 · effort S · N/A when: no JS UI framework detected

- **Why it matters (humans and agents):** Testing through roles and accessible names verifies behaviour users see and keeps tests stable across refactors.
- **How it is detected:** vitest or jest AND @testing-library/* in dependencies; one of them is partial.
- **How to fix:** Add Vitest + @testing-library/react (jest-dom, user-event) and test components by role/name.
- **Template reference:** [`frontend/src/components/ItemsPage.test.tsx`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/src/components/ItemsPage.test.tsx), [`frontend/src/test/setup.ts`](https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main/frontend/src/test/setup.ts)

<!-- END GENERATED CHECKS -->
<!-- markdownlint-enable MD037 MD049 MD050 -->
