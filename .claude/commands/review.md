---
description: Review the current branch (or a PR number) with the code-review skill
argument-hint: "[PR number | base ref]"
allowed-tools: Read, Grep, Glob, Bash(git diff:*), Bash(git log:*), Bash(git show:*), Bash(git status:*), Bash(gh pr view:*), Bash(gh pr diff:*), Bash(gh pr checks:*), Bash(make lint), Bash(make typecheck), Bash(make test)
---

Review this change using the `code-review` skill (`.agents/skills/code-review/SKILL.md`). Read the
skill first and follow its checklist and output format.

Target: `$ARGUMENTS` - a PR number reviews that PR (`gh pr diff <n>`); a ref reviews
`<ref>...HEAD`; empty reviews `origin/main...HEAD` plus uncommitted changes.

Prefer delegating to the `reviewer` subagent so the review is independent of the code's author. Do
not edit files. Report findings grouped by severity, then a verdict.
