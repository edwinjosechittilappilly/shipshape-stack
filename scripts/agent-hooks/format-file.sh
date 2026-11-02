#!/usr/bin/env bash
# Post-edit formatter (Claude PostToolUse(Edit|Write|MultiEdit), Codex PostToolUse(apply_patch),
# Cursor afterFileEdit). Formats ONLY the file(s) the agent just touched, so diffs stay small and
# there is no repo-wide churn. It never fails the edit: missing tools, odd paths and tool errors
# are ignored (CI's `make lint` is the real gate).
#
#   format-file.sh [--claude|--codex|--cursor]   < hook payload JSON
#
#   backend/**/*.py                          ruff format + ruff check --fix (via uv, no auto-install)
#   frontend/**/*.{ts,tsx,js,jsx,mjs,cjs,json,css,md}   prettier from frontend/node_modules
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/agent-hooks/lib.sh
. "$DIR/lib.sh"
hook_init "$@"

root="$HOOK_ROOT"

format_python() {
  local file=$1
  command -v uv >/dev/null 2>&1 || return 0
  # --no-sync: never touch the network or rebuild the venv from inside a hook.
  uv run --no-sync --project "$root/backend" ruff format "$file" >/dev/null 2>&1 || true
  uv run --no-sync --project "$root/backend" ruff check --fix --quiet "$file" >/dev/null 2>&1 || true
}

format_frontend() {
  local file=$1 prettier="$root/frontend/node_modules/.bin/prettier"
  [ -x "$prettier" ] || return 0
  (cd "$root/frontend" && "$prettier" --write --ignore-unknown "$file" >/dev/null 2>&1) || true
}

while IFS= read -r file; do
  if [ -z "$file" ] || [ ! -f "$file" ]; then continue; fi
  case "$file" in
    "$root"/backend/*.py) format_python "$file" ;;
    "$root"/frontend/node_modules/*) ;;
    "$root"/frontend/*.ts | "$root"/frontend/*.tsx | "$root"/frontend/*.js | "$root"/frontend/*.jsx | \
      "$root"/frontend/*.mjs | "$root"/frontend/*.cjs | "$root"/frontend/*.json | \
      "$root"/frontend/*.css | "$root"/frontend/*.md) format_frontend "$file" ;;
    *) ;;
  esac
done <<EOF
$(hook_payload files)
EOF

exit 0
