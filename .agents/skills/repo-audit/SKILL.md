---
name: repo-audit
description: "Use when asked to audit, score or grade a repository against best practices, find gaps in CI, tests, security, docs or agent-readiness, or plan (and optionally execute) improvements using the ShipShape template as the base. Runs a static scanner (Python stdlib only), adds a qualitative review, and produces a scorecard, prioritized fixes and a PR-sliced improvement plan."
---

# Repo audit

Evaluate any repository against the practices in the [ShipShape template](https://github.com/edwinjosechittilappilly/shipshape-stack), explain the shortcomings, and turn them into a
small-PR improvement plan an agent can execute. The scanner is **evidence**, not the verdict: you add judgement
(step 2) and you never weaken a check to raise a score.

This skill is self-contained. Copy this directory into any repo's `.claude/skills/` or `.agents/skills/`, or into
`~/.claude/skills/`; it needs only Python >= 3.11 (standard library) and git is optional. `<skill-dir>` below means
the directory containing this file.

## Workflow

### 1. Scan

```bash
python3 <skill-dir>/scripts/audit.py <repo> --format markdown   # human report
python3 <skill-dir>/scripts/audit.py <repo> --format json       # machine use (schema: references/rubric.md section 4)
```

Static analysis only: no network, no execution of the target's code, usually under a second. Useful options:
`--category security` (repeatable; scopes score and exit code), `--min-score 80` (exit 1 below),
`--template-url <base>` (links to a fork of the template), `--no-git` (plain directory walk instead of
`git ls-files`), `--list-checks`, `--dump-rubric`. Inside a git work tree it audits what git would commit, so
ignored local files (a gitignored `.env`, worktrees, caches) are not flagged.

Read the **stacks and traits** line first. If the detected stacks are wrong (a monorepo with an unusual layout, a
tooling-only `package.json`), say so and scope your conclusions; the scanner marks non-applicable checks `N/A`
instead of failing them, so check that the N/A set makes sense (for example a service with no Dockerfile detected
as a library would silently skip the Containers category).

### 2. Qualitative pass (what the scanner cannot see)

Work through the table in `references/rubric.md` section 3 and verify at least these, with real commands:

- **README works**: follow it literally; does a newcomer reach a running app and a green test run?
- **Tests assert behaviour**: open 3-5 tests from different areas; are mocks hiding the behaviour under test?
- **CI is actually green** on the default branch: `gh run list --branch <default> --limit 20`, then
  `gh run view <id> --log-failed` for failures (skip politely if `gh` is unavailable or unauthenticated, and say so).
- **Branch protection / repo settings** (`gh api repos/{owner}/{repo}/branches/<default>/protection`): is the
  aggregate check required?
- **Docs are current**: sample five documented commands/paths and confirm they exist.

Record every adjustment as `check id | scanner status | adjusted status | evidence`. Never change a status without
evidence you observed; keep both the scanner score and the adjusted score in the report.

### 3. Write the report

Use this shape (the markdown output of step 1 already contains the tables; add your judgement on top):

1. **Header**: repo name, detected stacks/traits, scanner score and grade, adjusted score and grade, date.
2. **Scorecard table**: category, weight, score, grade (N/A categories shown as excluded).
3. **Top 10 fixes** ranked by impact (`gain` = overall points won) then effort; for each: check id, evidence,
   fix, template link. Mention which are **quick wins** (effort S).
4. **Findings by category**: only what matters; evidence (paths, counts) not opinion.
5. **Adjustments** from step 2 with evidence.
6. **Not assessed / assumptions**: platform settings you could not read, stacks only partially supported.

Be specific and honest. A failing check is not an insult; say what it costs a human or an agent today
(for example "no required aggregate check: every renamed job silently un-protects main").

### 4. Plan the improvements as small PRs

Follow `references/improvement-playbook.md`. Slice so the **score rises fastest** and every PR is independently
mergeable (phases: safety, foundation, CI gate, quality + tests, security, hygiene + agent layer, deployment).
For each PR give:

- conventional title (`type(scope): subject`, lower-case, <= 72 chars)
- goal and the check ids it flips with the expected score delta
- files to add or adapt, each with the template source (the `template_refs` in the JSON / links in the report)
- adaptation notes for this stack
- verification commands, risk and rollback, dependencies on earlier PRs

Do not pad: if only four checks fail, plan two PRs. Skip slices whose checks already pass.

### 5. Optionally execute

Only when asked. For each PR in order: branch from the default branch, implement, verify with the project's own
commands (`make check` or equivalent), re-run the scanner on the branch, and put the score delta in the PR body
(`before -> after`, category deltas, check ids that changed). Stop and ask a human when a step needs credentials,
rotating a leaked secret, repository settings, or a design decision. Never merge your own PRs unless told to.

## Adapting, not copying, template files

The template is a Python + React "items" app. For the target repo:

- Get files from a local checkout of the template or by raw URL (see `references/improvement-playbook.md` section 6).
- Keep the **pattern** (aggregate `ci-success` gate, `permissions: {}`, SHA pins, timeouts, `Makefile` verbs,
  non-root pinned multi-stage Dockerfile, deny-listed secrets for agents) and rewrite the **content** for the
  target's languages, package manager, test runner and deploy model. Section 5 of the playbook maps each template
  file to what to change for Python, Node, Go, Java, Rust, Ruby and .NET.
- Do not import the example domain, frontend tooling for a repo without UI, or Kubernetes/Terraform when the target
  deploys elsewhere. If a check becomes irrelevant, explain why in the report; do not game it.
- Every command you write into `AGENTS.md`, a `Makefile` or a workflow must be one you ran successfully.

## Stack awareness

Checks are language-aware. The scanner detects Python, Node/TypeScript, Go, Rust, JVM (Java/Kotlin), Ruby, PHP and
.NET from manifests, plus frontend (UI framework dependency), React, "service" (web framework, Dockerfile or
workload manifests) and monorepo traits. Language-specific checks evaluate each detected language
(linter, formatter, type checker, lockfile, toolchain pin); statically typed languages are excluded from type checks;
GitHub-Actions-specific checks are `N/A` when another CI system is used; library repos skip container and e2e
checks. Other ecosystems (Elixir, Swift, Dart, ...) get the language-agnostic checks only; say so in the report.

## Rules

- Do not edit the scanner or rubric to make a particular repo pass. If a check is wrong for a stack, report it
  (with the repo layout that fools it) and apply a justified adjustment in your report.
- Never print secret values found by the scanner; paths only. Treat any `SEC-NO-SECRETS` failure as an incident:
  say that the credential must be rotated, not just deleted.
- Do not run the target repository's code to "confirm" findings unless asked; use its documented commands only
  in step 2/5 and only in a disposable checkout when it is untrusted.
- Keep the audit output out of the template itself: results belong in the target repo or your answer.

## Files

- `scripts/audit.py` - CLI and report rendering; `scripts/checks.py` - category table and registry entry;
  `scripts/checks_*.py` - the checks (id, weight, applicability, evaluator, remediation, template refs);
  `scripts/registry.py`, `scripts/repo_context.py` - framework and read-only repo view.
- `references/rubric.md` - scoring formula, stack detection, qualitative rubric, JSON schema, every check.
- `references/improvement-playbook.md` - ordering, PR slicing examples, adapting template files per stack.
- `tests/` - `python3 -m unittest discover -s <skill-dir>/tests -t <skill-dir>`.
