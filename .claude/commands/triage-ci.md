---
description: Diagnose a failing CI run for the current PR and fix it (or escalate)
argument-hint: "[run id | PR number]"
allowed-tools: Read, Grep, Glob, Edit, Write, Bash(git:*), Bash(gh pr checks:*), Bash(gh pr view:*), Bash(gh run list:*), Bash(gh run view:*), Bash(make:*)
---

Triage the failing CI for `$ARGUMENTS` (default: the PR for the current branch) using the `ci-triage`
skill (`.agents/skills/ci-triage/SKILL.md`). Read it first.

1. Identify the failing job (`gh pr checks`, `gh run view --log-failed`).
2. Reproduce locally with the SAME make target the job calls. Do not guess from logs alone.
3. Decide: real failure, flaky, or infrastructure. Never retry-until-green; never disable or loosen a check.
4. Real failure: fix it in a small commit, re-run the make target, push. Flaky/infra: say so with
   evidence and label `status: needs-human`.
