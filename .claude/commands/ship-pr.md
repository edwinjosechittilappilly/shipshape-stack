---
description: Run the checks, self-review, and open or update the PR for the current branch
argument-hint: "[issue number]"
allowed-tools: Read, Grep, Glob, Bash(git:*), Bash(gh:*), Bash(make:*), Bash(python3 scripts/ci/check_pr.py:*)
---

Ship the current branch as a pull request, following the `pull-request` skill
(`.agents/skills/pull-request/SKILL.md`). Read it first.

1. Confirm the branch is not `main` and the diff is one concern (split it if not - see sizing in the skill).
2. Run `make check`, plus any heavier rung of the verification ladder in `AGENTS.md` the change needs.
3. Self-review with the `code-review` skill; fix blockers and majors before continuing.
4. Write the title (Conventional Commits) and body (template headings, Verification table) and
   validate them with `make pr-check TITLE="..." BODY=<file>`.
5. Push with `git push -u origin HEAD` and open the PR as draft unless every check is green. Add
   labels per the skill, including `agent: authored`. Link the issue: `$ARGUMENTS`.

Stop and label the PR `status: needs-human` if you hit any escalation rule in `AGENTS.md`.
