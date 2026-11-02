import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import check_pr as cp

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = REPO_ROOT / ".github" / "pull_request_template.md"

GOOD_BODY = """\
## Summary

Users can now search items by title. The list endpoint accepts `q` and the UI shows a search box.

## Linked issue

Closes #42

## Changes

- **Backend:** `GET /api/v1/items?q=` filters with a case-insensitive match.
- **Frontend:** search box above the list, debounced.

## Verification

| Check | Command | Result |
| --- | --- | --- |
| Lint, types, unit tests | `make check` | pass (212 tests) |
| E2E (mocked API) | `make test-e2e` | pass |

## Risk and rollback

Additive; revert the PR.

## Checklist

- [x] Tests added or updated
"""


def codes(findings: list[cp.Finding], level: str | None = None) -> list[str]:
    return [f.code for f in findings if level is None or f.level == level]


class TitleTests(unittest.TestCase):
    def test_valid_titles(self) -> None:
        for title in [
            "feat: add search",
            "fix(api): handle empty title",
            "refactor(ui)!: rename Items component props",
            "ci: pin actions by sha",
            "build(deps): bump the minor-and-patch group with 3 updates",
            "revert: undo search",
            "chore(deps-dev): bump vitest",
            "feat: " + "x" * (72 - len("feat: ")),  # exactly 72
        ]:
            with self.subTest(title=title):
                self.assertEqual(cp.validate_title(title), [])

    def test_invalid_titles(self) -> None:
        cases = {
            "": "title-empty",
            "   ": "title-empty",
            "Add search": "title-format",
            "feat add search": "title-format",
            "feature: add search": "title-format",
            "feat: Add search": "title-case",
            "feat: add search.": "title-period",
            "feat: " + "x" * (73 - len("feat: ")): "title-length",
            " feat: add search": "title-whitespace",
        }
        for title, code in cases.items():
            with self.subTest(title=title):
                self.assertIn(code, codes(cp.validate_title(title), "error"))

    def test_none_title(self) -> None:
        self.assertEqual(codes(cp.validate_title(None)), ["title-empty"])  # type: ignore[arg-type]

    def test_malformed_title_message_lists_types(self) -> None:
        message = cp.validate_title("oops")[0].message
        for commit_type in ("feat", "fix", "security", "revert"):
            self.assertIn(commit_type, message)


class SectionParsingTests(unittest.TestCase):
    def test_comments_are_stripped_including_multiline(self) -> None:
        sections = cp.parse_sections("## Summary\n<!--\nmulti\nline\n-->\ntext\n")
        self.assertEqual(sections["summary"].strip(), "text")

    def test_heading_case_and_crlf(self) -> None:
        sections = cp.parse_sections("## SUMMARY\r\nhello\r\n## changes\r\n- a\r\n")
        self.assertEqual(sections["summary"].strip(), "hello")
        self.assertEqual(sections["changes"].strip(), "- a")

    def test_commented_out_heading_is_ignored(self) -> None:
        sections = cp.parse_sections("<!-- ## Summary -->\n## Changes\n- x\n")
        self.assertNotIn("summary", sections)

    def test_h3_is_content_not_a_section(self) -> None:
        sections = cp.parse_sections("## Changes\n### Backend\n- x\n")
        self.assertIn("### Backend", sections["changes"])


class BodyTests(unittest.TestCase):
    def test_good_body_passes_without_findings(self) -> None:
        self.assertEqual(cp.validate_body(GOOD_BODY), [])

    def test_raw_template_fails_on_required_sections(self) -> None:
        findings = cp.validate_body(TEMPLATE.read_text(encoding="utf-8"))
        errors = codes(findings, "error")
        self.assertEqual(errors.count("section-empty"), 2)  # Summary and Changes
        self.assertIn("verification-table", errors)
        self.assertIn("no-linked-issue", codes(findings, "warning"))

    def test_template_headings_match_checker(self) -> None:
        headings = [h.strip() for h in cp._HEADING_RE.findall(TEMPLATE.read_text(encoding="utf-8"))]
        self.assertEqual(headings, list(cp.KNOWN_SECTIONS))

    def test_empty_and_whitespace_body(self) -> None:
        self.assertEqual(codes(cp.validate_body("")), ["body-empty"])
        self.assertEqual(codes(cp.validate_body("  \n\n")), ["body-empty"])
        self.assertEqual(codes(cp.validate_body(None)), ["body-empty"])  # type: ignore[arg-type]

    def test_missing_required_sections(self) -> None:
        findings = cp.validate_body("## Summary\nDid a thing.\n")
        messages = [f.message for f in findings if f.code == "section-missing"]
        self.assertEqual(len(messages), 2)
        self.assertTrue(any("Changes" in m for m in messages))
        self.assertTrue(any("Verification" in m for m in messages))

    def test_comment_only_sections_are_empty(self) -> None:
        body = (
            "## Summary\n<!-- explain -->\n\n## Changes\n<!-- one line per behaviour -->\n\n"
            "## Verification\n<!-- table -->\n"
        )
        self.assertEqual(codes(cp.validate_body(body), "error"), ["section-empty"] * 3)

    def test_placeholder_text_is_empty(self) -> None:
        for placeholder in ["TBD", "n/a", "N/A.", "todo", "None", "-", "- ", "- [ ]", "...", "…", "<what changed>"]:
            with self.subTest(placeholder=placeholder):
                body = GOOD_BODY.replace("Users can now search items by title. The list endpoint accepts `q` and the UI shows a search box.", placeholder)
                self.assertIn("section-empty", codes(cp.validate_body(body), "error"))

    def test_label_only_bullets_are_empty_but_filled_ones_count(self) -> None:
        body = GOOD_BODY.split("## Changes")[0] + "## Changes\n\n- **Backend:**\n- **Frontend:**\n\n## Verification" + GOOD_BODY.split("## Verification")[1]
        self.assertIn("section-empty", codes(cp.validate_body(body), "error"))

    def test_verification_prose_without_table_fails(self) -> None:
        body = GOOD_BODY.split("| Check")[0] + "I ran everything and it passed.\n\n## Risk and rollback\nrevert\n"
        self.assertIn("verification-table", codes(cp.validate_body(body), "error"))

    def test_verification_table_with_only_blank_results_fails(self) -> None:
        body = GOOD_BODY.replace("pass (212 tests)", "").replace("| pass |", "|  |")
        self.assertIn("verification-table", codes(cp.validate_body(body), "error"))

    def test_verification_one_filled_row_is_enough(self) -> None:
        body = GOOD_BODY.replace("| `make test-e2e` | pass |", "| `make test-e2e` | |")
        self.assertEqual(cp.validate_body(body), [])

    def test_verification_table_without_separator_is_not_a_table(self) -> None:
        body = GOOD_BODY.replace("| --- | --- | --- |\n", "")
        self.assertIn("verification-table", codes(cp.validate_body(body), "error"))

    def test_verification_skipped_with_reason_counts_as_a_result(self) -> None:
        body = GOOD_BODY.replace("pass (212 tests)", "skipped: docs-only change").replace("| pass |", "| skipped: docs only |")
        self.assertEqual(cp.validate_body(body), [])

    def test_missing_linked_issue_is_only_a_warning(self) -> None:
        body = GOOD_BODY.replace("Closes #42", "")
        findings = cp.validate_body(body)
        self.assertEqual(codes(findings, "error"), [])
        self.assertEqual(codes(findings, "warning"), ["no-linked-issue"])

    def test_linked_issue_variants(self) -> None:
        for text in ["Closes #42", "fixes #7", "Refs owner/repo#9", "None", "N/A", "https://github.com/o/r/issues/12"]:
            with self.subTest(text=text):
                body = GOOD_BODY.replace("Closes #42", text)
                self.assertEqual(codes(cp.validate_body(body), "warning"), [])

    def test_linked_issue_section_absent_warns(self) -> None:
        body = GOOD_BODY.replace("## Linked issue\n\nCloses #42\n\n", "")
        self.assertEqual(codes(cp.validate_body(body), "warning"), ["no-linked-issue"])

    def test_breaking_requires_risk_section(self) -> None:
        body = GOOD_BODY.replace("Additive; revert the PR.", "<!-- todo -->")
        self.assertEqual(codes(cp.validate_body(body, breaking=True), "error"), ["breaking-risk"])
        self.assertEqual(codes(cp.validate_body(body, breaking=False), "error"), [])
        self.assertEqual(codes(cp.validate_body(GOOD_BODY, breaking=True), "error"), [])

    def test_unknown_section_warns(self) -> None:
        body = GOOD_BODY + "\n## Random notes\nhi\n"
        self.assertEqual(codes(cp.validate_body(body), "warning"), ["unknown-section"])

    def test_windows_line_endings(self) -> None:
        self.assertEqual(cp.validate_body(GOOD_BODY.replace("\n", "\r\n")), [])


class AnnotationTests(unittest.TestCase):
    def test_escaping(self) -> None:
        text = cp.annotation(cp.Finding("error", "a:b,c", "50% done\nnext"))
        self.assertEqual(text, "::error title=a%3Ab%2Cc::50%25 done%0Anext")


class CliTests(unittest.TestCase):
    def run_main(self, argv: list[str], env: dict[str, str] | None = None) -> tuple[int, str]:
        out = StringIO()
        with mock.patch.dict(os.environ, env or {}, clear=False), redirect_stdout(out):
            code = cp.main(argv)
        return code, out.getvalue()

    def write_body(self, tmp: str, text: str) -> str:
        path = Path(tmp, "body.md")
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_good_pr_exits_zero_and_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp, "summary.md")
            code, out = self.run_main(
                ["--title", "feat(api): add search", "--body-file", self.write_body(tmp, GOOD_BODY)],
                {"GITHUB_STEP_SUMMARY": str(summary), "GITHUB_ACTIONS": ""},
            )
            self.assertEqual(code, 0)
            self.assertIn("look good", out)
            self.assertIn("PR checks passed", summary.read_text(encoding="utf-8"))

    def test_template_fails_with_actionable_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp, "summary.md")
            code, out = self.run_main(
                ["--title", "feat: x", "--body-file", str(TEMPLATE)],
                {"GITHUB_STEP_SUMMARY": str(summary), "GITHUB_ACTIONS": "true"},
            )
            self.assertEqual(code, 1)
            self.assertIn("::error title=section-empty::", out)
            self.assertIn("::warning title=no-linked-issue::", out)
            text = summary.read_text(encoding="utf-8")
            self.assertIn("PR checks failed", text)
            self.assertIn("How to fix", text)

    def test_event_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp, "event.json")
            event.write_text(json.dumps({"pull_request": {"title": "fix: crash", "body": GOOD_BODY, "user": {"login": "me"}}}))
            code, _ = self.run_main(["--event-path", str(event)], {"GITHUB_STEP_SUMMARY": "", "GITHUB_ACTIONS": ""})
            self.assertEqual(code, 0)

    def test_event_payload_with_null_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp, "event.json")
            event.write_text(json.dumps({"pull_request": {"title": "fix: crash", "body": None, "user": {"login": "me"}}}))
            code, out = self.run_main(["--event-path", str(event)], {"GITHUB_STEP_SUMMARY": "", "GITHUB_ACTIONS": ""})
            self.assertEqual(code, 1)
            self.assertIn("body-empty", out)

    def test_dependabot_skips_body_but_not_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            def event(title: str) -> str:
                path = Path(tmp, "event.json")
                path.write_text(json.dumps({"pull_request": {"title": title, "body": "Bumps x.", "user": {"login": "dependabot[bot]"}}}))
                return str(path)

            env = {"GITHUB_STEP_SUMMARY": "", "GITHUB_ACTIONS": ""}
            self.assertEqual(self.run_main(["--event-path", event("build(deps): bump x from 1 to 2")], env)[0], 0)
            self.assertEqual(self.run_main(["--event-path", event("Bump x from 1 to 2")], env)[0], 1)

    def test_skip_body_flag(self) -> None:
        code, _ = self.run_main(["--title", "docs: tweak", "--skip-body"], {"GITHUB_STEP_SUMMARY": "", "GITHUB_ACTIONS": ""})
        self.assertEqual(code, 0)

    def test_breaking_title_needs_risk_section(self) -> None:
        body = GOOD_BODY.replace("## Risk and rollback\n\nAdditive; revert the PR.\n\n", "")
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self.run_main(
                ["--title", "feat(api)!: drop v0", "--body-file", self.write_body(tmp, body)],
                {"GITHUB_STEP_SUMMARY": "", "GITHUB_ACTIONS": ""},
            )
        self.assertEqual(code, 1)
        self.assertIn("breaking-risk", out)

    def test_non_pr_event_payload_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp, "event.json")
            event.write_text(json.dumps({"ref": "refs/heads/main"}))
            with self.assertRaises(SystemExit):
                self.run_main(["--event-path", str(event)], {"GITHUB_STEP_SUMMARY": ""})


class RenderSummaryTests(unittest.TestCase):
    def test_clean_summary(self) -> None:
        text = cp.render_summary("feat: x", [], body_skipped=False)
        self.assertIn("passed", text)
        self.assertIn("No problems found", text)

    def test_bot_note(self) -> None:
        self.assertIn("automated PRs", cp.render_summary("build: x", [], body_skipped=True))


if __name__ == "__main__":
    unittest.main()
