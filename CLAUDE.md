@AGENTS.md

## Claude Code specifics

- Project config lives in `.claude/`: `settings.json` (permissions + hooks), `skills/` (symlink to
  `.agents/skills`), `agents/reviewer.md` (read-only review subagent), `commands/` (`/review`, `/ship-pr`, `/triage-ci`).
- Skills load automatically from their `description`; name one explicitly (for example "use the pull-request skill")
  when starting a task that clearly matches.
- For an independent second opinion before opening a PR, delegate to the `reviewer` subagent (or run `/review`) instead of
  re-reading your own diff in the same context.
- Hooks run through `$CLAUDE_PROJECT_DIR/scripts/agent-hooks/`: a blocked Bash command prints the reason and the safe alternative
  on stderr; follow it. The Stop hook runs lint + typecheck for changed packages and may send you back to fix them once.
- `.claude/settings.json` is shared and reviewed. Put personal preferences (extra permissions, model) in
  `.claude/settings.local.json` (gitignored), never in the shared file.
- `git push` is not pre-approved; allow it in your local settings only for the autonomy level in
  `docs/agents/self-managed-prs.md` that this repo has granted.
- Use plan mode for anything that needs the `planning` skill, and keep context lean: read files with line ranges and prefer
  `make` targets over ad-hoc commands so results match CI.
