#!/usr/bin/env python3
"""Shell-command policy for coding agents. Called by guard-shell.sh; not a security boundary.

Reads ONE shell command on stdin. Exit codes: 0 = allowed, 10 = blocked (reasons on stdout,
one per line, each ending with the safe alternative), anything else = the policy itself broke
(the caller fails open and warns).

The command is tokenised with shlex (quote-aware, so `git commit -m "mention git push -f"` is
fine), split on `; && || | &` and newlines, and `bash -c "..."` / `eval "..."` payloads are
checked recursively. It stops honest mistakes and prompt-injected one-liners; it cannot stop
an agent determined to obfuscate (that is what branch protection and CODEOWNERS are for).

Protected branches default to main,master; override with AGENT_PROTECTED_BRANCHES=a,b.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys

BLOCKED = 10
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
WRAPPERS = {"sudo", "doas", "command", "nohup", "time", "exec", "builtin", "nice", "env"}
READERS = {
    "cat", "tac", "less", "more", "head", "tail", "bat", "batcat", "nl", "od", "xxd", "hexdump",
    "strings", "grep", "egrep", "fgrep", "rg", "ag", "ack", "awk", "sed", "cut", "sort", "uniq",
    "diff", "cmp", "source", ".", "base64", "vi", "vim", "nano", "emacs", "open", "code",
}  # fmt: skip
COPIERS = {"cp", "mv", "scp", "rsync", "install", "curl", "wget", "ln"}
ENV_FILE = re.compile(r"\.env(\.[^/]*|[*?\[].*)?")
ENV_ALLOWED = {".env.example", ".env.sample", ".env.template", ".env.dist"}
GIT_VALUE_FLAGS = {
    "commit": {"-m", "--message", "-F", "--file", "-C", "-c", "--author", "--date"},
    "push": {"-o", "--push-option", "--repo", "--receive-pack", "--exec"},
}
OPERATORS = set(";&|()")
REDIRECT_OUT = {">", ">>", ">&", ">|", "&>"}

PUSH_FORCE = (
    "Force-pushing rewrites shared history. Use `git push --force-with-lease origin <feature-branch>` "
    "(it refuses to clobber work you have not seen); never force-push main/master."
)
PUSH_PROTECTED = (
    "Pushing straight to a protected branch ({branch}) bypasses review and required CI. Push a "
    "feature branch (`git push -u origin HEAD`) and open a PR (skill: pull-request)."
)
PUSH_ALL = (
    "`git push --all/--mirror` would also push protected branches. Push the one branch you "
    "changed: `git push -u origin HEAD`."
)
RESET_HARD = (
    "`git reset --hard` destroys uncommitted work with no undo. Use `git stash`, "
    "`git restore <file>` for a single file, or `git reset --soft/--mixed`."
)
CLEAN_X = (
    "`git clean -fdx` deletes untracked AND ignored files (.env, .venv, node_modules, local data). "
    "Preview with `git clean -n`, then remove named paths explicitly."
)
NO_VERIFY = (
    "Skipping git hooks (--no-verify / -n) hides failures instead of fixing them. Run the hook's "
    "checks (`make check`, `pre-commit run --files <paths>`), fix the cause, then commit normally."
)
HOOKS_PATH = (
    "Changing core.hooksPath (or skipping hooks via SKIP=/HUSKY=0) disables the repo's guardrails. "
    "Leave hooks installed; if a hook is wrong, fix the hook in a PR."
)
RM_DANGER = (
    "Recursive delete of `{target}` is not allowed. Delete the specific build/cache directory you "
    "created (e.g. `rm -rf backend/.pytest_cache`)."
)
REMOTE_EXEC = (
    "Piping a download into a shell/interpreter runs unreviewed code. Download to a file "
    "(`curl -fsSLo /tmp/x.sh <url>`), read it, then run it deliberately - or use the package manager."
)
ENV_READ = (
    "`{target}` holds secrets and must not be read or copied by agents. Read `.env.example` for the "
    "variable names; ask the user for values; `docker compose` and `make` load .env on their own."
)
HOOKS_UNINSTALL = (
    "Uninstalling hooks disables the repo's guardrails. Leave them installed; fix the hook via a PR."
)
GH_ADMIN_MERGE = (
    "`gh pr merge --admin` bypasses branch protection. Wait for required checks and reviews; label "
    "the PR `status: needs-human` if it is stuck."
)
GH_APPROVE = (
    "Agents never approve PRs (least of all their own). Leave review to a human CODEOWNER; "
    "comment findings with `gh pr review --comment`."
)


def protected_branches() -> set[str]:
    raw = os.environ.get("AGENT_PROTECTED_BRANCHES", "main,master")
    return {b.strip() for b in raw.split(",") if b.strip()}


def scan(command: str) -> tuple[str, str]:
    """Return (normalised, masked). Normalised turns unquoted newlines into `;`; masked also
    blanks the inside of quoted strings so regexes do not fire on prose."""
    norm: list[str] = []
    mask: list[str] = []
    quote = ""
    i = 0
    while i < len(command):
        c = command[i]
        if quote:
            norm.append(c)
            mask.append(c if c == quote else " ")
            if c == "\\" and quote == '"' and i + 1 < len(command):
                i += 1
                norm.append(command[i])
                mask.append(" ")
            elif c == quote:
                quote = ""
        elif c == "\\" and i + 1 < len(command):
            nxt = command[i + 1]
            i += 1
            if nxt == "\n":
                norm.append(" ")
                mask.append(" ")
            else:
                norm += [c, nxt]
                mask += [c, nxt]
        elif c in "'\"":
            quote = c
            norm.append(c)
            mask.append(c)
        elif c == "\n":
            norm.append(" ; ")
            mask.append(" ; ")
        else:
            norm.append(c)
            mask.append(c)
        i += 1
    return "".join(norm), "".join(mask)


def tokenize(text: str) -> list[str]:
    lex = shlex.shlex(text, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        return list(lex)
    except ValueError:  # unbalanced quotes: degrade to whitespace split
        return text.split()


def segments(text: str) -> list[list[str]]:
    out: list[list[str]] = []
    current: list[str] = []
    skip_next = False
    for tok in tokenize(text):
        if skip_next:  # target of an output redirect
            skip_next = False
            continue
        if tok in REDIRECT_OUT:
            skip_next = True
            continue
        if tok and set(tok) <= OPERATORS:
            if current:
                out.append(current)
            current = []
            continue
        current.append(tok)
    if current:
        out.append(current)
    return out


def current_branch(cwd: str) -> str:
    try:
        res = subprocess.run(
            ["git", "-C", cwd, "symbolic-ref", "--short", "-q", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return ""
    return res.stdout.strip()


def flags_of(args: list[str]) -> tuple[set[str], set[str]]:
    """Return (long flags without values, single-letter flags from short clusters)."""
    longs: set[str] = set()
    shorts: set[str] = set()
    for a in args:
        if a == "--":
            break
        if re.fullmatch(r"--[A-Za-z0-9][A-Za-z0-9-]*(=.*)?", a):
            longs.add(a.split("=", 1)[0])
        elif re.fullmatch(r"-[A-Za-z0-9]+", a):
            shorts.update(a[1:])
    return longs, shorts


def drop_values(args: list[str], value_flags: set[str]) -> list[str]:
    out: list[str] = []
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a in value_flags:
            skip = True
            continue
        if any(a.startswith(f + "=") for f in value_flags if f.startswith("--")):
            continue
        if a.startswith("-m") and len(a) > 2 and "-m" in value_flags:  # -mMESSAGE
            continue
        out.append(a)
    return out


def check_git(assignments: dict[str, str], args: list[str], cwd: str) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(args) and args[i].startswith("-"):
        a = args[i]
        if a == "-C" and i + 1 < len(args):
            cwd = os.path.normpath(os.path.join(cwd, args[i + 1]))
            i += 2
        elif a == "-c" and i + 1 < len(args):
            if "core.hookspath" in args[i + 1].lower():
                out.append(HOOKS_PATH)
            i += 2
        elif a in ("--git-dir", "--work-tree", "--namespace"):
            i += 2
        else:
            i += 1
    if i >= len(args):
        return out
    sub, rest = args[i], args[i + 1 :]
    if sub in ("commit", "push", "merge", "rebase", "cherry-pick", "am", "revert"):
        if assignments.get("SKIP") or assignments.get("HUSKY") == "0" or assignments.get("LEFTHOOK") == "0":
            out.append(HOOKS_PATH)
    rest = drop_values(rest, GIT_VALUE_FLAGS.get(sub, set()))
    longs, shorts = flags_of(rest)
    if "--no-verify" in longs or (sub == "commit" and "n" in shorts):
        out.append(NO_VERIFY)
    positional = [a for a in rest if not a.startswith("-") or a == "-"]
    if sub == "push":
        out += check_push(longs, shorts, positional, cwd)
    elif sub == "reset" and "--hard" in longs:
        out.append(RESET_HARD)
    elif sub == "clean":
        forced = "--force" in longs or "f" in shorts
        if forced and ("x" in shorts or "X" in shorts):
            out.append(CLEAN_X)
    elif sub == "config" and not ({"--get", "--get-all", "--list", "-l", "--get-regexp"} & set(rest)):
        if any("core.hookspath" in a.lower() for a in rest):
            out.append(HOOKS_PATH)
    return out


def check_push(longs: set[str], shorts: set[str], positional: list[str], cwd: str) -> list[str]:
    out: list[str] = []
    refspecs = positional[1:]  # first positional is the remote
    if "--force" in longs or "f" in shorts or any(r.startswith("+") for r in refspecs):
        out.append(PUSH_FORCE)
    if "--all" in longs or "--mirror" in longs:
        out.append(PUSH_ALL)
    protected = protected_branches()
    targets: list[str] = []
    for ref in refspecs:
        dst = ref.split(":", 1)[1] if ":" in ref else ref
        dst = dst.lstrip("+").removeprefix("refs/heads/")
        targets.append(dst)
    if not refspecs or "HEAD" in targets:
        branch = current_branch(cwd)
        targets = [branch if t == "HEAD" else t for t in targets] + ([branch] if not refspecs else [])
    for t in targets:
        if t in protected:
            out.append(PUSH_PROTECTED.format(branch=t))
            break
    return out


def dangerous_target(target: str) -> bool:
    t = re.sub(r"/+\*?$", "", target) or "/"
    if t in {"/", "~", "$HOME", "${HOME}", ".", "..", ".git"} or t == os.path.expanduser("~"):
        return True
    return bool(re.fullmatch(r"/[^/]+|/(Users|home)/[^/]+", t))


def check_rm(args: list[str]) -> list[str]:
    longs, shorts = flags_of(args)
    if not ({"--recursive"} & longs or {"r", "R"} & shorts):
        return []
    targets = [a for a in args if not a.startswith("-")]
    for t in targets:
        if dangerous_target(t):
            return [RM_DANGER.format(target=t)]
    return []


def env_target(tok: str) -> str:
    tok = tok.split("=@", 1)[1] if "=@" in tok else tok.lstrip("@")
    base = os.path.basename(tok.rstrip("/"))
    if ENV_FILE.fullmatch(base) and base not in ENV_ALLOWED:
        return tok
    return ""


def check_env_read(cmd: str, tokens: list[str]) -> list[str]:
    """tokens includes the command word. Redirect targets for `>` were already dropped."""
    for idx, tok in enumerate(tokens):
        target = env_target(tok) if idx else ""
        if not target:
            continue
        after_stdin_redirect = idx > 0 and tokens[idx - 1] == "<"
        is_last = idx == len(tokens) - 1
        if cmd in READERS or after_stdin_redirect:
            return [ENV_READ.format(target=target)]
        if cmd in COPIERS and not is_last:
            return [ENV_READ.format(target=target)]
    return []


def check_gh(args: list[str]) -> list[str]:
    if args[:2] == ["pr", "merge"] and "--admin" in args:
        return [GH_ADMIN_MERGE]
    if args[:2] == ["pr", "review"] and ("--approve" in args or "-a" in args):
        return [GH_APPROVE]
    return []


def check_segment(tokens: list[str], cwd: str, depth: int) -> list[str]:
    assignments: dict[str, str] = {}
    while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
        key, _, value = tokens.pop(0).partition("=")
        assignments[key] = value
    while tokens and os.path.basename(tokens[0]) in WRAPPERS:
        wrapper = os.path.basename(tokens.pop(0))
        while tokens and (tokens[0].startswith("-") or (wrapper == "env" and "=" in tokens[0])):
            if wrapper == "env" and "=" in tokens[0]:
                key, _, value = tokens[0].partition("=")
                assignments[key] = value
            tokens.pop(0)
    if not tokens:
        return []
    cmd = os.path.basename(tokens[0])
    args = tokens[1:]
    out: list[str] = []
    if cmd in SHELLS:
        for j, a in enumerate(args[:-1]):
            if re.fullmatch(r"-[a-z]*c[a-z]*", a):
                out += check(args[j + 1], cwd, depth + 1)
                break
    elif cmd == "eval":
        text = " ".join(args)
        if re.search(r"(\$\(|`)\s*(curl|wget)\b", text):
            out.append(REMOTE_EXEC)
        out += check(text, cwd, depth + 1)
    elif cmd == "git":
        out += check_git(assignments, args, cwd)
    elif cmd == "gh":
        out += check_gh(args)
    elif cmd == "rm":
        out += check_rm(args)
    elif cmd == "pre-commit" and args[:1] == ["uninstall"]:
        out.append(HOOKS_UNINSTALL)
    out += check_env_read(cmd, tokens)
    return out


REMOTE_PIPE = re.compile(
    r"\b(curl|wget)\b[^;&\n]*\|\s*(sudo\s+(-\S+\s+)*)?("
    r"(ba|z|da|k)?sh\b|(python3?|node|perl|ruby)\b(\s+-)?\s*($|[;&|)]))"
)
REMOTE_SUBST = re.compile(r"\b((ba|z|da|k)?sh|source|\.)\s+<\(\s*(curl|wget)\b")


def check(command: str, cwd: str, depth: int = 0) -> list[str]:
    if depth > 3:
        return []
    norm, masked = scan(command)
    out: list[str] = []
    if REMOTE_PIPE.search(masked) or REMOTE_SUBST.search(masked):
        out.append(REMOTE_EXEC)
    for seg in segments(norm):
        out += check_segment(seg, cwd, depth)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", default=os.getcwd())
    cwd = parser.parse_args().cwd
    reasons = list(dict.fromkeys(check(sys.stdin.read(), cwd)))
    if reasons:
        print("\n".join(reasons))
        return BLOCKED
    return 0


if __name__ == "__main__":
    sys.exit(main())
