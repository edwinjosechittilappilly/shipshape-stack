#!/usr/bin/env bash
# Stop gate (Claude Stop, Codex Stop, Cursor stop). Before the agent declares itself done, run the
# fast, scoped checks for the packages it changed. If they fail, hand the failure back to the agent
# instead of letting it stop with a red tree.
#
#   stop-gate.sh [--claude|--codex|--cursor]   < hook payload JSON
#
# What runs (only for packages with changes in the working tree, staged/unstaged/untracked):
#   backend/   make -C backend lint typecheck      (needs uv)
#   frontend/  make -C frontend lint typecheck     (needs frontend/node_modules)
# Tests are NOT run here: they are slower and belong to `make check` / CI.
#
# Loop guard: if the stop event is already a continuation (Claude/Codex `stop_hook_active`, Cursor
# `loop_count` >= 1) the gate lets the agent stop, so a check that cannot be fixed never traps it.
# Opt out entirely with AGENT_STOP_GATE=0 (e.g. when the agent is only exploring).
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/agent-hooks/lib.sh
. "$DIR/lib.sh"
hook_init "$@"

[ "${AGENT_STOP_GATE:-1}" = 0 ] && hook_stop_allow
[ "$(hook_payload loop-active)" = 1 ] && hook_stop_allow

root="$HOOK_ROOT"
cd "$root" 2>/dev/null || hook_stop_allow
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || hook_stop_allow

backend_changed=0
frontend_changed=0
while IFS= read -r line; do
  path="${line#???}"       # drop the two status columns and the space
  path="${path##* -> }"    # renames: keep the new path
  path="${path#\"}"
  case "$path" in
    backend/*) backend_changed=1 ;;
    frontend/*) frontend_changed=1 ;;
    *) ;;
  esac
done <<EOF
$(git status --porcelain --untracked-files=all 2>/dev/null)
EOF

failures=""
notes=""

# run_check <label> <dir> : run `make -k -C <dir> lint typecheck`, collect the tail of any failure.
run_check() {
  local label=$1 dir=$2 output
  if ! output="$(make --no-print-directory -k -C "$dir" lint typecheck 2>&1)"; then
    failures="${failures}
--- ${label}: make -C ${dir} lint typecheck (last 40 lines) ---
$(printf '%s\n' "$output" | tail -n 40)
"
  fi
}

if [ "$backend_changed" = 1 ]; then
  if command -v uv >/dev/null 2>&1 && [ -f backend/Makefile ]; then
    run_check backend backend
  else
    notes="${notes}backend checks skipped (uv or backend/Makefile missing). "
  fi
fi
if [ "$frontend_changed" = 1 ]; then
  if [ -d frontend/node_modules ] && command -v npm >/dev/null 2>&1 && [ -f frontend/Makefile ]; then
    run_check frontend frontend
  else
    notes="${notes}frontend checks skipped (run 'make -C frontend setup' first). "
  fi
fi

if [ -n "$failures" ]; then
  hook_stop_block "stop-gate: checks failed for the packages you changed. Fix the cause (do not edit
the checks or use --no-verify), re-run the same command, then finish. Set AGENT_STOP_GATE=0 only if
the user asked you to stop with known failures, and say so in your summary.
${failures}"
fi

[ -n "$notes" ] && echo "stop-gate: ${notes}" >&2
hook_stop_allow
