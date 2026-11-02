# Agent skills

Skills are short, task-focused playbooks that agents load **on demand**, so `AGENTS.md` stays small.
They follow the open [Agent Skills](https://agentskills.io) layout: one directory per skill containing a
`SKILL.md` with YAML frontmatter (`name`, `description`) and markdown instructions. The `description` says
*when* to use the skill; agents match on it.

This directory is the single source of truth:

- Codex, Cursor and other tools that read `AGENTS.md` find skills here (`.agents/skills/`).
- Claude Code reads `.claude/skills`, a symlink to `../.agents/skills`.

| Skill | Use it when | Key outputs |
| --- | --- | --- |
| [`pull-request`](pull-request/SKILL.md) | opening/updating a PR, answering review | conventional title, template body, Verification table, labels |
| [`writing-issues`](writing-issues/SKILL.md) | filing or refining an issue; deciding `agent: ready` | testable acceptance criteria, agent-ready task |
| [`planning`](planning/SKILL.md) | multi-package/multi-PR work, data model or contract changes | plan in `docs/plans/`, ADR in `docs/adr/`, PR slices |
| [`integration-tests`](integration-tests/SKILL.md) | backend tests against real Postgres, migrations | focused tests in `backend/tests/integration/` |
| [`playwright-tests`](playwright-tests/SKILL.md) | browser tests, mocked vs fullstack, a11y | specs in `frontend/e2e/` |
| [`code-review`](code-review/SKILL.md) | reviewing a diff/PR, self-review before opening a PR | severity-ranked findings + verdict |
| [`ci-triage`](ci-triage/SKILL.md) | a CI check is red | reproduction, classification, fix-forward or revert |
| [`repo-audit`](repo-audit/SKILL.md) | scoring any repo against this template's practices; planning improvements with this template as the baseline | scored report (`python3 .agents/skills/repo-audit/scripts/audit.py <repo> --format markdown`) and a prioritized PR-by-PR plan |

## Typical order

`writing-issues` -> `planning` (if large) -> implement with `integration-tests` / `playwright-tests` ->
`code-review` (self) -> `pull-request` -> `ci-triage` when red -> `code-review` findings from others.

Outside a feature's life cycle: `repo-audit` scores a repository (this one or another) against these practices and
turns the gaps into a PR-by-PR plan, which then flows through `planning` -> `writing-issues`.

## Adding or changing a skill

1. Create `.agents/skills/<kebab-name>/SKILL.md` starting with:

   ```markdown
   ---
   name: <kebab-name>            # must equal the directory name
   description: "Use when <trigger>. <what it covers>."   # quote it if it contains ': '
   ---
   ```

2. Write for an agent with no context: when to use, steps with exact commands, a checklist, good/bad examples.
   Reference repo files by path instead of copying their contents. Keep it under ~250 lines; split if longer.
3. Keep skills tool-agnostic: no references to one vendor's slash commands or hooks (those live in `.claude/`, `.codex/`, `.cursor/`).
4. Add the skill to the table above and to `AGENTS.md` ("Skills").
5. Do not duplicate rules between skills; link to the owning skill or doc instead.
