#!/usr/bin/env python3
"""Compute pull-request labels (type, breaking, size) from the PR title and diff stats.

Everything interesting is a pure function so it can be unit-tested without GitHub:

    parse_title(title)            -> ParsedTitle | None
    type_label(commit_type)       -> "type: feature" | ...
    changed_lines(files)          -> int   (lockfiles and generated files excluded)
    size_label(lines)             -> "size/XS" ... "size/XL"
    desired_labels(title, body, files) -> list[str]
    plan_label_changes(current, desired) -> (to_add, to_remove)

The CLI is used by .github/workflows/pr-labeler.yml. That workflow runs on `pull_request_target`, so this file is
executed from the *base* branch checkout and must never import or execute anything from the PR head.

Python >= 3.11, standard library only.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

# Conventional Commit type -> label (kept in sync with .github/labels.yml and docs/ci.md).
TYPE_LABELS: dict[str, str] = {
    "feat": "type: feature",
    "fix": "type: bug",
    "docs": "type: docs",
    "chore": "type: chore",
    "build": "type: chore",
    "style": "type: chore",
    "revert": "type: chore",
    "refactor": "type: refactor",
    "test": "type: test",
    "ci": "type: ci",
    "perf": "type: perf",
    "security": "type: security",
}
COMMIT_TYPES: tuple[str, ...] = tuple(TYPE_LABELS)

BREAKING_LABEL = "breaking-change"
TYPE_PREFIX = "type: "
SIZE_PREFIX = "size/"

# Upper bounds (exclusive) for each size bucket; anything at or above the last bound is XL.
SIZE_BUCKETS: tuple[tuple[int, str], ...] = (
    (10, "size/XS"),
    (50, "size/S"),
    (200, "size/M"),
    (500, "size/L"),
)
SIZE_XL = "size/XL"
ALL_SIZE_LABELS: tuple[str, ...] = tuple(label for _, label in SIZE_BUCKETS) + (SIZE_XL,)

MAX_TITLE_LENGTH = 72

# Files that are machine-written. Counting them would make a one-line dependency bump look like an XL change.
EXCLUDED_BASENAMES = frozenset(
    {
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "uv.lock",
        "poetry.lock",
        "Pipfile.lock",
        "Cargo.lock",
        "go.sum",
        "Gemfile.lock",
        "composer.lock",
        "Chart.lock",
        ".terraform.lock.hcl",
    }
)
EXCLUDED_GLOBS: tuple[str, ...] = (
    "*.lock",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.snap",
    "*.generated.*",
    "*_pb2.py",
    "*_pb2_grpc.py",
    "*/generated/*",
    "generated/*",
    "*/__generated__/*",
    "*/dist/*",
    "dist/*",
)

_TITLE_RE = re.compile(
    r"^(?P<type>[a-z]+)"
    r"(?:\((?P<scope>[^()\s]+)\))?"
    r"(?P<breaking>!)?"
    r": (?P<subject>\S.*)$"
)
_BREAKING_FOOTER_RE = re.compile(r"^BREAKING[ -]CHANGE:\s*\S", re.MULTILINE)


@dataclass(frozen=True)
class ParsedTitle:
    type: str
    scope: str | None
    breaking: bool
    subject: str


def parse_title(title: str) -> ParsedTitle | None:
    """Parse `type(scope)!: subject`. Returns None when the title is not a known Conventional Commit."""
    match = _TITLE_RE.match(title.strip())
    if match is None or match["type"] not in TYPE_LABELS:
        return None
    return ParsedTitle(
        type=match["type"],
        scope=match["scope"],
        breaking=match["breaking"] is not None,
        subject=match["subject"],
    )


def type_label(commit_type: str) -> str | None:
    return TYPE_LABELS.get(commit_type)


def has_breaking_footer(body: str) -> bool:
    """True when the PR body carries a `BREAKING CHANGE: ...` footer (Conventional Commits spec)."""
    return _BREAKING_FOOTER_RE.search(body or "") is not None


def is_excluded(path: str) -> bool:
    """True for lockfiles and generated artefacts that should not count towards PR size."""
    normalized = path.replace("\\", "/").removeprefix("./")
    if PurePosixPath(normalized).name in EXCLUDED_BASENAMES:
        return True
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in EXCLUDED_GLOBS)


def changed_lines(files: Iterable[dict[str, object]]) -> int:
    """Sum additions + deletions over `files` (GitHub `pulls/{n}/files` shape), skipping excluded paths."""
    total = 0
    for entry in files:
        path = str(entry.get("filename", ""))
        if is_excluded(path):
            continue
        total += int(entry.get("additions", 0) or 0) + int(entry.get("deletions", 0) or 0)
    return total


def size_label(lines: int) -> str:
    for upper_bound, label in SIZE_BUCKETS:
        if lines < upper_bound:
            return label
    return SIZE_XL


def desired_labels(title: str, body: str, files: Iterable[dict[str, object]]) -> list[str]:
    """Labels this automation owns for the given PR: at most one type label, optional breaking, exactly one size."""
    labels: list[str] = []
    parsed = parse_title(title)
    if parsed is not None:
        labels.append(TYPE_LABELS[parsed.type])
    if (parsed is not None and parsed.breaking) or has_breaking_footer(body):
        labels.append(BREAKING_LABEL)
    labels.append(size_label(changed_lines(files)))
    return labels


def _is_owned(label: str) -> bool:
    return label.startswith((TYPE_PREFIX, SIZE_PREFIX)) or label == BREAKING_LABEL


def plan_label_changes(current: Sequence[str], desired: Sequence[str]) -> tuple[list[str], list[str]]:
    """Return (to_add, to_remove).

    The automation owns every `type: *`, `size/*` label and `breaking-change`; all other labels (area, status,
    agent, ...) are never touched here. This guarantees a single size label and a single type label at a time.
    A title that does not parse yields no type label, so a stale one is removed rather than left misleading.
    """
    current_set = set(current)
    desired_set = set(desired)
    to_add = sorted(desired_set - current_set)
    to_remove = sorted(label for label in current_set - desired_set if _is_owned(label))
    return to_add, to_remove


def _load_files(path: str) -> list[dict[str, object]]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    # `gh api --paginate` without --slurp can emit concatenated arrays; accept a list of lists too.
    if data and isinstance(data[0], list):
        data = [entry for page in data for entry in page]
    return data


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--title", required=True)
    parser.add_argument("--body-file", help="File containing the PR body (optional).")
    parser.add_argument("--files-json", required=True, help="JSON from `gh api repos/{o}/{r}/pulls/{n}/files`.")
    parser.add_argument("--current-labels", default="", help="Comma-separated labels currently on the PR.")
    args = parser.parse_args(argv)

    body = ""
    if args.body_file:
        with open(args.body_file, encoding="utf-8") as handle:
            body = handle.read()
    desired = desired_labels(args.title, body, _load_files(args.files_json))
    current = [label for label in args.current_labels.split(",") if label]
    to_add, to_remove = plan_label_changes(current, desired)
    json.dump({"desired": desired, "add": to_add, "remove": to_remove}, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
