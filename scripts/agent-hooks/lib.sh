#!/usr/bin/env bash
# Shared plumbing for the agent hook entry points (guard-shell.sh, format-file.sh, stop-gate.sh).
# Source it; do not execute it. One implementation serves Claude Code, Codex and Cursor:
#
#   * the tool is chosen by flag (--claude | --codex | --cursor) or auto-detected from the payload;
#   * Claude and Codex block with "exit 2 + reason on stderr";
#   * Cursor blocks with a JSON document on stdout (permission: deny / followup_message).
#
# Bash 3.2 compatible (macOS default). python3 does all JSON work, so there is no jq dependency.
# shellcheck shell=bash

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# AGENT_HOOKS_ROOT lets tests point the hooks at a scratch repository.
# shellcheck disable=SC2034  # read by the scripts that source this file
HOOK_ROOT="${AGENT_HOOKS_ROOT:-$(cd "$HOOK_DIR/../.." && pwd)}"
HOOK_FORMAT=auto
HOOK_PAYLOAD='{}'

# hook_payload <query> [args]: ask payload.py about the JSON we received on stdin.
hook_payload() {
  printf '%s' "$HOOK_PAYLOAD" | python3 "$HOOK_DIR/payload.py" "$@"
}

# hook_init "$@": parse flags, slurp the stdin payload, resolve the tool format.
hook_init() {
  local arg
  for arg in "$@"; do
    case "$arg" in
      --claude) HOOK_FORMAT=claude ;;
      --codex) HOOK_FORMAT=codex ;;
      --cursor) HOOK_FORMAT=cursor ;;
      *) ;;
    esac
  done
  if [ ! -t 0 ]; then
    HOOK_PAYLOAD="$(cat)"
  fi
  if [ -z "$HOOK_PAYLOAD" ]; then
    HOOK_PAYLOAD='{}'
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "agent-hooks: python3 not found; hook skipped (fail open)." >&2
    exit 0
  fi
  if [ "$HOOK_FORMAT" = auto ]; then
    HOOK_FORMAT="$(hook_payload detect)"
  fi
}

# hook_block <message>: refuse a tool call (PreToolUse / beforeShellExecution).
hook_block() {
  if [ "$HOOK_FORMAT" = cursor ]; then
    python3 "$HOOK_DIR/payload.py" deny "$1"
    exit 0
  fi
  printf '%s\n' "$1" >&2
  exit 2
}

# hook_allow: let a tool call through. Cursor permission hooks must answer in JSON.
hook_allow() {
  if [ "$HOOK_FORMAT" = cursor ]; then
    python3 "$HOOK_DIR/payload.py" allow
  fi
  exit 0
}

# hook_stop_block <message>: refuse to let the agent stop and feed <message> back to it.
hook_stop_block() {
  if [ "$HOOK_FORMAT" = cursor ]; then
    python3 "$HOOK_DIR/payload.py" followup "$1"
    exit 0
  fi
  printf '%s\n' "$1" >&2
  exit 2
}

# hook_stop_allow: let the agent stop. Codex and Cursor expect JSON on stdout for Stop hooks.
hook_stop_allow() {
  if [ "$HOOK_FORMAT" != claude ]; then
    echo '{}'
  fi
  exit 0
}
