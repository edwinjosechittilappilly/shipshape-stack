#!/usr/bin/env bash
# Pre-execution guard for agent shell commands (Claude PreToolUse(Bash), Codex PreToolUse(Bash),
# Cursor beforeShellExecution). Blocks destructive or guardrail-disabling commands and tells the
# agent what to do instead. The rules live in guard_policy.py; this file is the protocol adapter.
#
#   guard-shell.sh [--claude|--codex|--cursor]   < hook payload JSON
#
# Humans can bypass for a whole session by launching the agent with AGENT_HOOKS_BYPASS=1. An
# agent cannot: the variable is read from the hook's own environment, not from the command text.
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/agent-hooks/lib.sh
. "$DIR/lib.sh"
hook_init "$@"

if [ "${AGENT_HOOKS_BYPASS:-0}" = 1 ]; then
  hook_allow
fi

command_text="$(hook_payload command)"
if [ -z "$command_text" ]; then
  hook_allow
fi
cwd="$(hook_payload cwd)"

reasons="$(printf '%s' "$command_text" | python3 "$DIR/guard_policy.py" --cwd "$cwd")"
status=$?

case "$status" in
  0) hook_allow ;;
  10)
    hook_block "BLOCKED by guard-shell (scripts/agent-hooks):
${reasons}
See docs/agents/hooks.md. If this is a false positive, ask the user; do not work around it." ;;
  *)
    echo "guard-shell: policy check failed (status ${status}); allowing. Please report this." >&2
    hook_allow ;;
esac
