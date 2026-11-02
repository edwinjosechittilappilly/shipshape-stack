import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pr_labels as pl


def f(name: str, additions: int = 0, deletions: int = 0) -> dict[str, object]:
    return {"filename": name, "additions": additions, "deletions": deletions}


class ParseTitleTests(unittest.TestCase):
    def test_plain(self) -> None:
        parsed = pl.parse_title("feat: add items endpoint")
        assert parsed is not None
        self.assertEqual((parsed.type, parsed.scope, parsed.breaking), ("feat", None, False))

    def test_scope_and_breaking(self) -> None:
        parsed = pl.parse_title("refactor(api)!: drop v0 routes")
        assert parsed is not None
        self.assertEqual((parsed.type, parsed.scope, parsed.breaking), ("refactor", "api", True))

    def test_breaking_without_scope(self) -> None:
        parsed = pl.parse_title("fix!: change error shape")
        assert parsed is not None
        self.assertTrue(parsed.breaking)

    def test_malformed_titles_are_rejected(self) -> None:
        bad = [
            "",
            "add items endpoint",  # no type
            "feat add items",  # no colon
            "feat:add items",  # no space after colon
            "feat:  ",  # empty subject
            "feat(): add items",  # empty scope
            "feat(a b): x",  # whitespace in scope
            "feat(api: x",  # unbalanced paren
            "Feat: add items",  # type must be lower-case
            "feature: add items",  # unknown type
            "feat !: add items",  # space before bang
            "feat!!: add items",
            "(api): add items",
        ]
        for title in bad:
            with self.subTest(title=title):
                self.assertIsNone(pl.parse_title(title))

    def test_surrounding_whitespace_is_ignored_by_parser(self) -> None:
        self.assertIsNotNone(pl.parse_title("  fix: x  "))

    def test_every_type_has_a_label(self) -> None:
        for commit_type in pl.COMMIT_TYPES:
            self.assertIsNotNone(pl.parse_title(f"{commit_type}: something"))
            self.assertTrue(pl.type_label(commit_type).startswith("type: "))  # type: ignore[union-attr]

    def test_type_label_mapping_matches_contract(self) -> None:
        expected = {
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
        self.assertEqual(pl.TYPE_LABELS, expected)


class BreakingFooterTests(unittest.TestCase):
    def test_footer_detected(self) -> None:
        self.assertTrue(pl.has_breaking_footer("text\n\nBREAKING CHANGE: removes /v0"))
        self.assertTrue(pl.has_breaking_footer("BREAKING-CHANGE: removes /v0"))

    def test_mentions_without_footer_do_not_count(self) -> None:
        self.assertFalse(pl.has_breaking_footer("This is not a BREAKING CHANGE"))
        self.assertFalse(pl.has_breaking_footer("BREAKING CHANGE:"))
        self.assertFalse(pl.has_breaking_footer(""))
        self.assertFalse(pl.has_breaking_footer(None))  # type: ignore[arg-type]


class SizeTests(unittest.TestCase):
    def test_boundaries(self) -> None:
        cases = {
            0: "size/XS",
            9: "size/XS",
            10: "size/S",
            49: "size/S",
            50: "size/M",
            199: "size/M",
            200: "size/L",
            499: "size/L",
            500: "size/XL",
            100_000: "size/XL",
        }
        for lines, label in cases.items():
            with self.subTest(lines=lines):
                self.assertEqual(pl.size_label(lines), label)

    def test_additions_and_deletions_both_count(self) -> None:
        self.assertEqual(pl.changed_lines([f("a.py", 4, 5), f("b.py", 1, 0)]), 10)

    def test_lockfiles_excluded(self) -> None:
        files = [
            f("frontend/package-lock.json", 9000, 4000),
            f("backend/uv.lock", 800, 100),
            f("deploy/helm/app/Chart.lock", 30, 0),
            f("infra/terraform/envs/prod/.terraform.lock.hcl", 50, 0),
            f("go.sum", 70, 0),
            f("backend/src/app/main.py", 3, 2),
        ]
        self.assertEqual(pl.changed_lines(files), 5)

    def test_generated_and_built_files_excluded(self) -> None:
        files = [
            f("frontend/dist/assets/index-abc.js", 5000, 0),
            f("frontend/src/api/generated/client.ts", 700, 0),
            f("backend/src/app/schema_pb2.py", 300, 0),
            f("frontend/public/vendor.min.js", 900, 0),
            f("frontend/src/__snapshots__/app.test.tsx.snap", 40, 0),
            f("frontend/src/App.tsx", 7, 0),
        ]
        self.assertEqual(pl.changed_lines(files), 7)

    def test_lookalike_names_are_not_excluded(self) -> None:
        # Only exact lockfile names are skipped: a source file mentioning "lock" still counts.
        self.assertFalse(pl.is_excluded("backend/src/app/lock.py"))
        self.assertFalse(pl.is_excluded("docs/package-lock-policy.md"))
        self.assertFalse(pl.is_excluded("src/distance.py"))
        self.assertTrue(pl.is_excluded("./uv.lock"))
        self.assertTrue(pl.is_excluded("a\\b\\package-lock.json"))

    def test_dotfile_prefix_is_preserved(self) -> None:
        # Regression guard: stripping "./" must not eat the leading dot of dotfiles.
        self.assertTrue(pl.is_excluded(".terraform.lock.hcl"))
        self.assertFalse(pl.is_excluded(".github/workflows/ci.yml"))

    def test_missing_counts_default_to_zero(self) -> None:
        self.assertEqual(pl.changed_lines([{"filename": "a.py"}, {"filename": "b.py", "additions": None}]), 0)

    def test_only_excluded_files_is_xs(self) -> None:
        self.assertEqual(pl.size_label(pl.changed_lines([f("uv.lock", 5000, 5000)])), "size/XS")


class DesiredLabelsTests(unittest.TestCase):
    def test_feature(self) -> None:
        self.assertEqual(pl.desired_labels("feat(ui): add dark mode", "", [f("a.ts", 20, 0)]), ["type: feature", "size/S"])

    def test_breaking_bang(self) -> None:
        labels = pl.desired_labels("fix(api)!: change error shape", "", [f("a.py", 1, 1)])
        self.assertEqual(labels, ["type: bug", "breaking-change", "size/XS"])

    def test_breaking_footer_only(self) -> None:
        labels = pl.desired_labels("feat: x", "BREAKING CHANGE: y", [f("a.py", 600, 0)])
        self.assertEqual(labels, ["type: feature", "breaking-change", "size/XL"])

    def test_unparseable_title_still_gets_size(self) -> None:
        self.assertEqual(pl.desired_labels("Update stuff", "", [f("a", 1, 0)]), ["size/XS"])

    def test_exactly_one_size_label(self) -> None:
        labels = pl.desired_labels("chore: x", "", [f("a", 120, 0)])
        self.assertEqual(sum(label.startswith("size/") for label in labels), 1)


class PlanTests(unittest.TestCase):
    def test_replaces_stale_size_and_type(self) -> None:
        add, remove = pl.plan_label_changes(
            ["size/S", "type: bug", "area: backend"], ["type: feature", "size/M"]
        )
        self.assertEqual(add, ["size/M", "type: feature"])
        self.assertEqual(remove, ["size/S", "type: bug"])

    def test_never_touches_foreign_labels(self) -> None:
        add, remove = pl.plan_label_changes(
            ["area: ci", "status: blocked", "agent: authored", "dependencies", "run: kind-e2e"], ["size/XS"]
        )
        self.assertEqual(add, ["size/XS"])
        self.assertEqual(remove, [])

    def test_removes_breaking_when_no_longer_applicable(self) -> None:
        _, remove = pl.plan_label_changes(["breaking-change", "size/XS"], ["size/XS"])
        self.assertEqual(remove, ["breaking-change"])

    def test_idempotent_when_already_correct(self) -> None:
        self.assertEqual(pl.plan_label_changes(["type: ci", "size/L"], ["type: ci", "size/L"]), ([], []))

    def test_multiple_existing_size_labels_collapse_to_one(self) -> None:
        add, remove = pl.plan_label_changes(["size/XS", "size/XL"], ["size/XL"])
        self.assertEqual((add, remove), ([], ["size/XS"]))

    def test_unparseable_title_drops_stale_type_label(self) -> None:
        _, remove = pl.plan_label_changes(["type: feature"], ["size/XS"])
        self.assertEqual(remove, ["type: feature"])


class CliTests(unittest.TestCase):
    def test_cli_outputs_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = Path(tmp, "files.json")
            # Paginated output may arrive as a list of pages.
            files.write_text(json.dumps([[f("a.py", 30, 0)], [f("uv.lock", 9999, 0)]]))
            out = StringIO()
            with redirect_stdout(out):
                code = pl.main(
                    [
                        "--title",
                        "docs: explain ci",
                        "--files-json",
                        str(files),
                        "--current-labels",
                        "size/XL,area: docs",
                    ]
                )
        self.assertEqual(code, 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["desired"], ["type: docs", "size/S"])
        self.assertEqual(result["add"], ["size/S", "type: docs"])
        self.assertEqual(result["remove"], ["size/XL"])


if __name__ == "__main__":
    unittest.main()
