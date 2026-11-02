# Agent hooks

Hooks are small scripts that the agent tool runs around its own actions. They turn "please don't" from a sentence
in `AGENTS.md` into something enforced. They are guardrails against honest mistakes and prompt-injected one-liners,
**not a security boundary**: a determined actor can obfuscate a command. Real enforcement of "nobody merges unreviewed
code" is branch protection and CODEOWNERS ([`self-managed-prs.md`](self-managed-prs.md)).

## Overview

| Hook script | Claude Code | Codex | Cursor | Enforces |
| --- | --- | --- | --- | --- |
| `guard-shell.sh` | `PreToolUse` (Bash) | `PreToolUse` (Bash) | `beforeShellExecution` | Blocks dangerous or guardrail-disabling shell commands |
| `format-file.sh` | `PostToolUse` (Edit, Write, MultiEdit) | `PostToolUse` (Edit, Write, apply_patch) | `afterFileEdit` | Formats only the file just edited |
| `stop-gate.sh` | `Stop` | `Stop` | `stop` | Runs lint and typecheck for changed packages before the agent stops |
| `test-hooks.sh` | n/a | n/a | n/a | Self-test with Claude, Codex and Cursor payloads (`make hooks-test`, CI) |

Wiring: [`.claude/settings.json`](../../.claude/settings.json), [`.codex/hooks.json`](../../.codex/hooks.json),
[`.cursor/hooks.json`](../../.cursor/hooks.json). Implementation: [`scripts/agent-hooks/`](../../scripts/agent-hooks).

## How the scripts stay tool-agnostic

All three scripts source `lib.sh`, which reads the JSON payload on stdin and asks `payload.py` (Python 3 standard
library, no `jq`) for the command, the edited files, the working directory and the loop-guard state. The tool is chosen
by a flag (`--claude`, `--codex`, `--cursor`) and auto-detected from the payload when the flag is absent.

| Concern | Claude Code | Codex | Cursor |
| --- | --- | --- | --- |
| Shell command in payload | `tool_input.command` | `tool_input.command` | `command` |
| Edited file in payload | `tool_input.file_path` | patch text in `tool_input.command` (`*** Update File: path`) | `file_path` |
| Block a tool call | exit `2`, reason on stderr | exit `2`, reason on stderr | exit `0` with `{"permission":"deny","agent_message":...}` |
| Allow a tool call | exit `0` | exit `0` | exit `0` with `{"permission":"allow"}` (invalid output blocks) |
| Block stopping | exit `2`, reason on stderr | exit `2`, reason on stderr | `{"followup_message": ...}` |
| Loop guard | `stop_hook_active` | `stop_hook_active` | `loop_count` (and `loop_limit` in config) |
| Stop allowed | no output | `{}` on stdout | `{}` on stdout |

## `guard-shell.sh`

Reads one shell command and checks it with the policy in `guard_policy.py`. The command is split into
statements (`;`, `&&`, `||`, `|`, newlines), parsed with shell quoting rules (so a commit message that merely
mentions `git push -f` is fine), and `bash -c "..."` / `eval` payloads are checked recursively.

| Blocked | Why | Safe alternative the agent is told |
| --- | --- | --- |
| `git push --force`, `-f`, `+refspec` | Rewrites shared history | `git push --force-with-lease origin <feature-branch>` |
| `git push` to `main`/`master` (explicit, `HEAD:main`, `--delete`, or a bare push while on main), `--all`/`--mirror` | Bypasses review and required CI | Push a feature branch and open a PR |
| `git reset --hard` | Destroys uncommitted work | `git stash`, `git restore <file>`, `reset --soft/--mixed` |
| `git clean -fdx` (force + x) | Deletes ignored files such as `.env` and `.venv` | `git clean -n` to preview, remove named paths |
| `--no-verify`, `git commit -n`, `SKIP=...`, `HUSKY=0` | Hides failures instead of fixing them | Fix the cause; run `pre-commit run --files ...` |
| `git config core.hooksPath`, `git -c core.hooksPath=...`, `pre-commit uninstall` | Disables the guardrails | Fix the hook in a PR |
| `rm -rf /`, `~`, `$HOME`, `.`, `..`, `.git`, `/usr`, `/Users/x` | Catastrophic | Delete the specific directory you created |
| `curl ... \| sh`, `bash <(curl ...)`, `eval "$(curl ...)"` | Runs unreviewed code | Download, read, then run deliberately |
| `cat`, `grep`, `head`, `cp`, `curl -d @` ... on `.env*` (not `.env.example`) | Leaks secrets into the model context | Read `.env.example`; ask the user for values |
| `gh pr merge --admin` | Bypasses branch protection | Wait for checks; label `status: needs-human` |
| `gh pr review --approve` | Agents never approve | `gh pr review --comment` |

Protected branches default to `main,master`; set `AGENT_PROTECTED_BRANCHES=main,release` to change them.

If the policy script itself crashes, the hook allows the command and prints a warning (a bug in the guard
must not brick the session).

## `format-file.sh`

Formats only the file(s) in the payload, so diffs stay small:

- `backend/**/*.py`: `uv run --no-sync --project backend ruff format <file>` then `ruff check --fix --quiet <file>`
- `frontend/**/*.{ts,tsx,js,jsx,mjs,cjs,json,css,md}`: `frontend/node_modules/.bin/prettier --write --ignore-unknown <file>`
- anything else, `node_modules`, missing files, missing tools: silently ignored

It always exits 0. It does not install anything (`--no-sync`, local prettier only); run `make setup` once.
CI's `make lint` is the real formatting gate.

## `stop-gate.sh`

When the agent tries to finish, `git status` decides which packages changed (staged, unstaged or untracked):

- `backend/` changed: `make -C backend lint typecheck` (needs `uv`)
- `frontend/` changed: `make -C frontend lint typecheck` (needs `frontend/node_modules`)
- docs-only or clean tree: nothing runs

On failure the agent is told to continue, with the last 40 lines of each failing target. Tests are deliberately
not run here (slow); `make check` and CI cover them. Missing tools skip that package with a note rather than blocking.

**Loop guard:** if the stop event is already a continuation (`stop_hook_active`, or Cursor `loop_count >= 1`)
the gate lets the agent stop. An unfixable failure therefore costs at most one extra turn. The agent is expected
to report remaining failures in its summary and label the PR `status: needs-human`.

## Legitimate bypasses

| Need | How | Who |
| --- | --- | --- |
| Skip all command guards for a session | Launch the tool with `AGENT_HOOKS_BYPASS=1` | A human, deliberately |
| Stop the stop-gate (exploration, known red tree) | `AGENT_STOP_GATE=0` in the environment | A human; an agent may only do so if the user asked, and must say so |
| Different protected branches | `AGENT_PROTECTED_BRANCHES=...` | A human |
| A rule is wrong | Fix `guard_policy.py` and add a case to `test-hooks.sh` in a PR | Anyone |
| Run one blocked command yourself | Run it in your own terminal | A human |

The variables are read from the hook process environment, so an agent cannot enable a bypass by prefixing a command with
`AGENT_HOOKS_BYPASS=1`. Never add a bypass to a shared settings file.

## Extending

1. Add the rule to `guard_policy.py` (a message constant naming the safe alternative, a check in the matching
   `check_*` function).
2. Add one blocking and one allowed case to `test-hooks.sh` (`expect_block` / `expect_allow`). Include a near-miss
   that must stay allowed, because false positives are what make people disable hooks.
3. `make hooks-test` and `shellcheck scripts/agent-hooks/*.sh`.
4. To support another tool, add its flag in `lib.sh`, its payload shape in `payload.py`, and its config file; then add a
   shape to `json_for` in the test.
5. Prefer fewer, sharper rules. A hook that cries wolf gets bypassed and then protects nothing.

## Tool-specific notes

- **Claude Code:** commands use `$CLAUDE_PROJECT_DIR`. Hook output on stderr with exit `2` is shown to the model.
  `.claude/settings.json` also carries `permissions.deny` rules (secrets, force-push) as a second layer.
- **Codex:** project hooks load only when the project is trusted; new or changed hooks must be reviewed once with
  `/hooks`. Commands resolve the repo root with `git rev-parse --show-toplevel`, so they work from subdirectories.
- **Cursor:** project hooks run from the repository root. Permission hooks must print valid JSON; invalid output blocks the
  action, which is why `guard-shell.sh --cursor` always answers with `allow` or `deny`.
