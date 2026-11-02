#!/usr/bin/env python3
"""Validate a pull request title and description against the repository contract.

Title:  Conventional Commits `type(scope)!: subject`, lower-case subject, no trailing period, <= 72 characters.
Body:   sections from .github/pull_request_template.md. `Summary`, `Changes` and `Verification` must have real
        content (HTML comments and placeholder text do not count) and the Verification table needs at least one
        row with a result. A missing linked issue is only a warning.

Usage:
    python3 scripts/ci/check_pr.py --title "feat(api): add items" --body-file body.md
    python3 scripts/ci/check_pr.py                      # reads $GITHUB_EVENT_PATH (pull_request event)

In GitHub Actions it prints workflow annotations (::error / ::warning) and appends a Markdown report to
$GITHUB_STEP_SUMMARY. Exit code is 1 when there is at least one error, 0 otherwise.

Python >= 3.11, standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pr_labels import COMMIT_TYPES, MAX_TITLE_LENGTH, parse_title

REQUIRED_SECTIONS: tuple[str, ...] = ("Summary", "Changes", "Verification")
KNOWN_SECTIONS: tuple[str, ...] = (
    "Summary",
    "Linked issue",
    "Changes",
    "Verification",
    "Screenshots",
    "Risk and rollback",
    "Out of scope",
    "Checklist",
)
# Authors whose PRs are machine-generated: their bodies are not expected to follow the template.
BOT_AUTHORS = frozenset({"dependabot[bot]", "renovate[bot]", "github-actions[bot]"})

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HEADING_RE = re.compile(r"^##[ \t]+(?P<name>.+?)[ \t]*#*[ \t]*$", re.MULTILINE)
# Lines that look like content but say nothing: empty bullets/checkboxes, ellipses, bare placeholders.
_EMPTY_LINE_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\[[ xX]\])?\s*[.…_\-*:]*\s*$")
_PLACEHOLDER_RE = re.compile(
    r"^\s*(?:[-*+]\s*)?(?:n/?a|none|tbd|todo|wip|\.{2,}|…|<[^>]*>)\s*\.?\s*$", re.IGNORECASE
)
# Template bullets such as "- **Backend:**" label a sub-section but contain no content.
_LABEL_ONLY_RE = re.compile(r"^\s*[-*+]\s*(?:\*\*[^*]+:\*\*|[A-Za-z ]+:)\s*$")
_ISSUE_REF_RE = re.compile(
    r"(?:(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs?|relates? to|part of)\s*:?\s*)?"
    r"(?:[\w.-]+/[\w.-]+)?(?:#\d+|https://github\.com/[\w.-]+/[\w.-]+/issues/\d+)",
    re.IGNORECASE,
)
_NO_ISSUE_RE = re.compile(r"^\s*(?:[-*+]\s*)?(?:n/?a|none|no issue|not applicable)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    level: str  # "error" | "warning"
    code: str
    message: str


def strip_comments(text: str) -> str:
    return _COMMENT_RE.sub("", text)


def parse_sections(body: str) -> dict[str, str]:
    """Map `## Heading` -> content (comments stripped). Matching is case-insensitive; the first duplicate wins."""
    cleaned = strip_comments(body.replace("\r\n", "\n"))
    matches = list(_HEADING_RE.finditer(cleaned))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        sections.setdefault(match["name"].strip().lower(), cleaned[match.end() : end].strip("\n"))
    return sections


def meaningful_lines(content: str) -> list[str]:
    """Lines of `content` that carry information (no blanks, empty bullets, label-only bullets or placeholders)."""
    lines = []
    for line in content.splitlines():
        if _EMPTY_LINE_RE.match(line) or _PLACEHOLDER_RE.match(line) or _LABEL_ONLY_RE.match(line):
            continue
        if re.match(r"^\s*```", line):
            continue
        lines.append(line.strip())
    return lines


def table_rows(content: str) -> list[list[str]]:
    """Data rows of the first Markdown table: header and separator rows are dropped."""
    rows: list[list[str]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")) or len(stripped) < 2:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        rows.append(cells)
    if len(rows) < 2:
        return []
    _header, separator, *data = rows
    if not all(re.fullmatch(r":?-+:?", cell) for cell in separator if cell != ""):
        # No separator row: this is not a valid table.
        return []
    return data


def validate_title(title: str) -> list[Finding]:
    findings: list[Finding] = []
    title = title or ""
    types = ", ".join(COMMIT_TYPES)
    if not title.strip():
        return [Finding("error", "title-empty", "PR title is empty.")]
    if len(title) > MAX_TITLE_LENGTH:
        findings.append(
            Finding("error", "title-length", f"Title is {len(title)} characters; the limit is {MAX_TITLE_LENGTH}.")
        )
    if title != title.strip():
        findings.append(Finding("error", "title-whitespace", "Title has leading or trailing whitespace."))
    parsed = parse_title(title)
    if parsed is None:
        findings.append(
            Finding(
                "error",
                "title-format",
                "Title must look like `type(scope)!: subject` (scope and `!` optional) with one of: "
                f"{types}. Example: `feat(api): add item search`.",
            )
        )
        return findings
    if parsed.subject[0].isupper():
        findings.append(Finding("error", "title-case", "Subject must start with a lower-case letter."))
    if parsed.subject.rstrip().endswith("."):
        findings.append(Finding("error", "title-period", "Subject must not end with a period."))
    return findings


def validate_body(body: str, *, breaking: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    body = body or ""
    if not body.strip():
        return [Finding("error", "body-empty", "PR description is empty. Fill in .github/pull_request_template.md.")]
    sections = parse_sections(body)

    for name in REQUIRED_SECTIONS:
        key = name.lower()
        if key not in sections:
            findings.append(Finding("error", "section-missing", f"Missing required section `## {name}`."))
            continue
        content = sections[key]
        if not meaningful_lines(content):
            findings.append(
                Finding("error", "section-empty", f"Section `## {name}` is empty (comments and placeholders do not count).")
            )

    verification = sections.get("verification")
    if verification is not None and meaningful_lines(verification):
        rows = table_rows(verification)
        filled = [row for row in rows if row and row[-1] and not _PLACEHOLDER_RE.match(row[-1])]
        if not filled:
            findings.append(
                Finding(
                    "error",
                    "verification-table",
                    "`## Verification` needs a table row with a result, e.g. `| Unit tests | `make test` | pass |`.",
                )
            )

    risk = sections.get("risk and rollback", "")
    if breaking and not meaningful_lines(risk):
        findings.append(
            Finding(
                "error",
                "breaking-risk",
                "Breaking change (`!` in the title): describe impact and rollback in `## Risk and rollback`.",
            )
        )

    linked = sections.get("linked issue", "")
    linked_lines = [line for line in linked.splitlines() if line.strip()]
    has_ref = any(_ISSUE_REF_RE.search(line) for line in linked_lines)
    explicitly_none = any(_NO_ISSUE_RE.match(line) for line in linked_lines)
    if not has_ref and not explicitly_none:
        findings.append(
            Finding(
                "warning",
                "no-linked-issue",
                "No linked issue. Add `Closes #123` under `## Linked issue`, or write `None` if there is no issue.",
            )
        )

    unknown = [name for name in re.findall(r"^##[ \t]+(.+?)[ \t]*$", strip_comments(body), re.MULTILINE)]
    known = {name.lower() for name in KNOWN_SECTIONS}
    for name in unknown:
        if name.strip().lower() not in known:
            findings.append(
                Finding("warning", "unknown-section", f"Unrecognised section `## {name.strip()}` (ignored).")
            )
    return findings


def _escape_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape_data(text).replace(":", "%3A").replace(",", "%2C")


def annotation(finding: Finding) -> str:
    return f"::{finding.level} title={_escape_property(finding.code)}::{_escape_data(finding.message)}"


def render_summary(title: str, findings: Sequence[Finding], *, body_skipped: bool) -> str:
    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]
    status = "failed" if errors else "passed"
    lines = [f"## PR checks {status}", "", f"Title: `{title}`", ""]
    if body_skipped:
        lines += ["_Body rules skipped for automated PRs (title still checked)._", ""]
    if not findings:
        lines.append("No problems found.")
    for heading, group in (("Errors (must fix)", errors), ("Warnings", warnings)):
        if group:
            lines += [f"### {heading}", ""]
            lines += [f"- **{f.code}**: {f.message}" for f in group]
            lines.append("")
    if errors:
        lines += [
            "How to fix: edit the PR title or description (this check re-runs automatically) and see "
            "`.agents/skills/pull-request/SKILL.md`. Validate locally with "
            '`make pr-check TITLE="..." BODY=path/to/body.md`.',
            "",
        ]
    return "\n".join(lines)


def _read_event(path: str) -> tuple[str, str, str]:
    with open(path, encoding="utf-8") as handle:
        event = json.load(handle)
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        raise SystemExit(f"{path} is not a pull_request event payload.")
    author = (pull_request.get("user") or {}).get("login", "")
    return pull_request.get("title") or "", pull_request.get("body") or "", author


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--title", help="PR title (default: from the event payload).")
    parser.add_argument("--body-file", help="File with the PR body (default: from the event payload).")
    parser.add_argument("--event-path", default=os.environ.get("GITHUB_EVENT_PATH"))
    parser.add_argument("--author", default="", help="PR author login; bot authors skip body rules.")
    parser.add_argument("--skip-body", action="store_true", help="Only validate the title.")
    args = parser.parse_args(argv)

    title, body, author = args.title, "", args.author
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    if args.title is None or (args.body_file is None and not args.skip_body):
        if not args.event_path:
            parser.error("pass --title and --body-file, or run inside Actions with GITHUB_EVENT_PATH set")
        event_title, event_body, event_author = _read_event(args.event_path)
        title = event_title if args.title is None else args.title
        body = event_body if args.body_file is None else body
        author = author or event_author

    body_skipped = args.skip_body or author in BOT_AUTHORS
    findings = validate_title(title)
    if not body_skipped:
        parsed = parse_title(title)
        findings += validate_body(body, breaking=bool(parsed and parsed.breaking))

    in_actions = bool(os.environ.get("GITHUB_ACTIONS"))
    for finding in findings:
        print(annotation(finding) if in_actions else f"{finding.level.upper()}: [{finding.code}] {finding.message}")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(render_summary(title, findings, body_skipped=body_skipped) + "\n")

    errors = [f for f in findings if f.level == "error"]
    if not errors:
        print("PR title and description look good." + (f" ({len(findings)} warning(s))" if findings else ""))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
