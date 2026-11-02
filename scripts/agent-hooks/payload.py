#!/usr/bin/env python3
"""Tiny JSON helper for the agent hook scripts (no jq dependency).

Claude Code, Codex and Cursor all pipe a JSON document to hook commands on stdin, but the
shapes differ. This module hides the differences so the shell scripts stay tool-agnostic:

    Claude  {"tool_name": "Bash", "tool_input": {"command": "..."}, "stop_hook_active": false}
    Codex   same as Claude, plus "turn_id"; edits arrive as an apply_patch text blob
    Cursor  {"hook_event_name": "beforeShellExecution", "command": "...", "cwd": "..."}
            {"hook_event_name": "afterFileEdit", "file_path": "...", "edits": [...]}
            {"hook_event_name": "stop", "status": "completed", "loop_count": 0}

Usage: payload.py <query>  (JSON on stdin; a missing or unparsable payload behaves like `{}`)

    detect       claude | codex | cursor
    command      the shell command being run ("" if none)
    files        absolute paths of files being edited, one per line
    cwd          working directory the tool call runs in
    loop-active  "1" if this stop event is already a continuation (loop guard), else "0"

    deny <msg>        Cursor permission response that blocks the action
    allow             Cursor permission response that allows the action
    followup <msg>    Cursor stop response that sends <msg> back to the agent
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$", re.MULTILINE)
PATCH_MOVE = re.compile(r"^\*\*\* Move to: (.+?)\s*$", re.MULTILINE)
FILE_KEYS = ("file_path", "path", "notebook_path", "filePath")


def load() -> dict[str, Any]:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def detect(p: dict[str, Any]) -> str:
    event = p.get("hook_event_name")
    if "conversation_id" in p or "cursor_version" in p:
        return "cursor"
    if isinstance(event, str) and event[:1].islower():  # beforeShellExecution, afterFileEdit, stop
        return "cursor"
    if "turn_id" in p:
        return "codex"
    if "tool_input" not in p and any(k in p for k in ("command", "file_path", "loop_count")):
        return "cursor"
    return "claude"


def tool_input(p: dict[str, Any]) -> dict[str, Any]:
    ti = p.get("tool_input")
    if isinstance(ti, dict):
        return ti
    if isinstance(ti, str):
        return {"command": ti}
    return {}


def command(p: dict[str, Any]) -> str:
    candidates = [p.get("command"), tool_input(p).get("command"), tool_input(p).get("cmd")]
    for value in candidates:
        if isinstance(value, list):
            value = " ".join(str(v) for v in value)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def cwd(p: dict[str, Any]) -> str:
    value = p.get("cwd")
    if isinstance(value, str) and value:
        return value
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def files(p: dict[str, Any]) -> list[str]:
    found: list[str] = []
    ti = tool_input(p)
    for source in (p, ti):
        for key in FILE_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value:
                found.append(value)
    edits = ti.get("edits") or p.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict) and isinstance(edit.get("file_path"), str):
                found.append(edit["file_path"])
    text = command(p)
    if "*** Begin Patch" in text:  # Codex apply_patch carries the whole patch as text
        found += PATCH_FILE.findall(text) + PATCH_MOVE.findall(text)
    base = cwd(p)
    seen: dict[str, None] = {}
    for item in found:
        seen[item if os.path.isabs(item) else os.path.normpath(os.path.join(base, item))] = None
    return list(seen)


def loop_active(p: dict[str, Any]) -> bool:
    if p.get("stop_hook_active"):
        return True
    count = p.get("loop_count")
    return isinstance(count, int) and count >= 1


def main(argv: list[str]) -> int:
    query = argv[1] if len(argv) > 1 else ""
    message = argv[2] if len(argv) > 2 else ""
    if query == "deny":
        print(json.dumps({"permission": "deny", "user_message": message, "agent_message": message}))
    elif query == "allow":
        print(json.dumps({"permission": "allow"}))
    elif query == "followup":
        print(json.dumps({"followup_message": message}))
    else:
        p = load()
        if query == "detect":
            print(detect(p))
        elif query == "command":
            print(command(p))
        elif query == "files":
            print("\n".join(files(p)))
        elif query == "cwd":
            print(cwd(p))
        elif query == "loop-active":
            print("1" if loop_active(p) else "0")
        else:
            sys.stderr.write(__doc__ or "")
            return 64
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
