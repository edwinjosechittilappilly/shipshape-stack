"""Behavioural tests for repo-audit using throwaway fixture repositories (no network, no git needed)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(SKILL_DIR, "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import audit  # noqa: E402
import checks  # noqa: E402
from fixtures import SHA, good_repo_files, make_repo, workflow, write_tree  # noqa: E402
from repo_context import Repo  # noqa: E402

CLI = [sys.executable, os.path.join(SCRIPTS, "audit.py")]


def scan(files: dict[str, str], **kw) -> dict:
    with make_repo(files) as root:
        return audit.run_audit(Repo(root, use_git=False), **kw)


def status(report: dict, check_id: str) -> str:
    return next(c["status"] for c in report["checks"] if c["id"] == check_id)


def evidence(report: dict, check_id: str) -> str:
    return next(c["evidence"] for c in report["checks"] if c["id"] == check_id)


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([*CLI, *args], capture_output=True, text=True, timeout=60)


class ScoringTests(unittest.TestCase):
    def test_empty_repo_fails_with_meaningful_top_fixes(self):
        report = scan({})
        self.assertEqual(report["score"]["grade"], "F")
        self.assertLess(report["score"]["overall"], 20)
        top = report["top_fixes"]
        self.assertGreaterEqual(len(top), 8)
        self.assertLessEqual(len(top), 10)
        for must in ("CI-EXISTS", "TEST-UNIT", "AGT-INSTRUCTIONS"):
            self.assertIn(must, top)
        self.assertEqual(status(report, "DOC-README"), "fail")
        for cid in top:
            c = next(x for x in report["checks"] if x["id"] == cid)
            self.assertTrue(c["remediation"])
            self.assertTrue(c["template_refs"], f"{cid} has no template reference")
            self.assertGreater(c["gain"], 0)

    def test_top_fixes_are_sorted_by_score_gain(self):
        report = scan({"README.md": "# x\n"})
        gains = [next(c["gain"] for c in report["checks"] if c["id"] == cid) for cid in report["top_fixes"]]
        self.assertEqual(gains, sorted(gains, reverse=True))

    def test_minimal_good_repo_scores_high_and_has_no_unexpected_failures(self):
        report = scan(good_repo_files())
        self.assertGreaterEqual(report["score"]["overall"], 85, [(c["id"], c["evidence"]) for c in report["checks"] if c["status"] in ("fail", "partial")])
        self.assertIn(report["score"]["grade"], ("A", "B"))
        errors = [c["id"] for c in report["checks"] if "internal error" in c["evidence"]]
        self.assertEqual(errors, [])

    def test_overall_is_the_weighted_mean_of_category_scores(self):
        report = scan(good_repo_files())
        live = [c for c in report["categories"] if c["score"] is not None]
        expected = sum(c["weight"] * c["score"] for c in live) / sum(c["weight"] for c in live)
        self.assertAlmostEqual(report["score"]["overall"], expected, delta=0.15)

    def test_category_weights_sum_to_100(self):
        self.assertEqual(sum(c.weight for c in checks.CATEGORIES), 100)

    def test_partial_counts_half(self):
        # README is a stub (partial) and everything else absent: DOC-README contributes half its weight.
        report = scan({"README.md": "# Hello\n"})
        self.assertEqual(status(report, "DOC-README"), "partial")
        next(c for c in report["checks"] if c["id"] == "DOC-README")
        self.assertEqual(next(c["points"] for c in report["checks"] if c["id"] == "DOC-README"), 0.5)

    def test_grade_boundaries(self):
        for score, grade in ((100, "A"), (90, "A"), (89.9, "B"), (80, "B"), (79.9, "C"), (70, "C"), (60, "D"), (59.9, "F"), (0, "F")):
            self.assertEqual(audit.grade_for(score), grade, score)


class ApplicabilityTests(unittest.TestCase):
    def test_no_frontend_excludes_frontend_category(self):
        report = scan(good_repo_files())
        cat = next(c for c in report["categories"] if c["id"] == "frontend")
        self.assertFalse(cat["applicable"])
        self.assertIsNone(cat["score"])
        fe = [c for c in report["checks"] if c["category"] == "frontend"]
        self.assertTrue(fe and all(c["status"] == "na" and c["points"] is None for c in fe))
        self.assertFalse(report["repo"]["flags"]["frontend"])

    def test_react_frontend_enables_frontend_checks(self):
        files = {"frontend/package.json": json.dumps({"dependencies": {"react": "19.0.0"}, "devDependencies": {"typescript": "5", "eslint-plugin-jsx-a11y": "6"}}), "frontend/tsconfig.json": '{"compilerOptions": {"strict": true}}'}
        report = scan(files)
        self.assertTrue(report["repo"]["flags"]["react"])
        self.assertEqual(status(report, "FE-TS-STRICT"), "pass")
        self.assertEqual(status(report, "FE-A11Y-LINT"), "partial")  # lint rules but no axe tests
        self.assertEqual(status(report, "FE-REACT-DOCTOR"), "fail")

    def test_vue_app_gets_frontend_checks_but_not_react_doctor(self):
        report = scan({"package.json": json.dumps({"dependencies": {"vue": "3"}})})
        self.assertNotEqual(status(report, "FE-TS-STRICT"), "na")
        self.assertEqual(status(report, "FE-REACT-DOCTOR"), "na")

    def test_language_aware_go_repo(self):
        files = {"go.mod": "module x\n\ngo 1.23\n\nrequire github.com/a/b v1.0.0\n", "go.sum": "x\n", ".golangci.yml": "linters: {}\n", "main.go": "package main\n", "main_test.go": "package main\nimport \"testing\"\nfunc TestX(t *testing.T) { if 1 != 1 { t.Error(\"no\") } }\n"}
        report = scan(files)
        self.assertIn("go", report["repo"]["stacks"])
        self.assertEqual(status(report, "QUAL-LINT"), "pass")
        self.assertEqual(status(report, "QUAL-TYPES"), "na")  # statically typed: not penalised
        self.assertEqual(status(report, "QUAL-STRICT"), "na")
        self.assertEqual(status(report, "DX-TOOLCHAIN"), "pass")
        self.assertEqual(status(report, "QUAL-LOCKFILES"), "pass")
        self.assertEqual(status(report, "TEST-CONFIG"), "pass")

    def test_python_without_linter_or_lockfile_is_flagged(self):
        files = {"pyproject.toml": '[project]\nname = "x"\nversion = "1"\ndependencies = ["requests"]\n'}
        report = scan(files)
        self.assertEqual(status(report, "QUAL-LINT"), "fail")
        self.assertEqual(status(report, "QUAL-LOCKFILES"), "fail")
        write = {**files, "uv.lock": "v=1\n", "ruff.toml": "line-length = 100\n"}
        report = scan(write)
        self.assertEqual(status(report, "QUAL-LINT"), "pass")
        self.assertEqual(status(report, "QUAL-LOCKFILES"), "pass")

    def test_library_without_deployables_skips_container_category(self):
        report = scan({"pyproject.toml": '[project]\nname = "lib"\nversion = "1"\n'})
        cat = next(c for c in report["categories"] if c["id"] == "containers")
        self.assertFalse(cat["applicable"])

    def test_non_github_ci_does_not_fail_github_specific_checks(self):
        report = scan({".gitlab-ci.yml": "test:\n  script:\n    - pytest\n"})
        self.assertEqual(status(report, "CI-EXISTS"), "pass")
        self.assertEqual(status(report, "CI-PINNED"), "na")
        self.assertEqual(status(report, "CI-PERMISSIONS"), "na")
        self.assertEqual(status(report, "CI-TEST"), "pass")

    def test_dependency_and_build_directories_are_ignored(self):
        files = {"node_modules/pkg/.env": "TOKEN=1\n", "node_modules/pkg/test_x.py": "assert 1\n", "vendor/x/id_rsa": "k\n"}
        report = scan(files)
        self.assertEqual(status(report, "SEC-NO-SECRETS"), "pass")
        self.assertEqual(report["repo"]["files_scanned"], 0)


class CiChecksTests(unittest.TestCase):
    def test_sha_pinned_vs_tag_pinned_actions(self):
        self.assertEqual(status(scan({".github/workflows/ci.yml": workflow()}), "CI-PINNED"), "pass")
        tag = scan({".github/workflows/ci.yml": workflow(pin="v4")})
        self.assertEqual(status(tag, "CI-PINNED"), "fail")
        self.assertIn("actions/checkout@v4", evidence(tag, "CI-PINNED"))

    def test_mixed_pinning_is_partial(self):
        wf = workflow(f"      - uses: actions/cache@v4\n      - uses: actions/setup-node@{SHA}\n")
        self.assertEqual(status(scan({".github/workflows/ci.yml": wf}), "CI-PINNED"), "partial")

    def test_commented_out_uses_lines_are_ignored(self):
        wf = workflow("      # - uses: evil/action@main\n")
        self.assertEqual(status(scan({".github/workflows/ci.yml": wf}), "CI-PINNED"), "pass")

    def test_missing_permissions_detected(self):
        self.assertEqual(status(scan({".github/workflows/ci.yml": workflow(permissions=False)}), "CI-PERMISSIONS"), "fail")
        self.assertEqual(status(scan({".github/workflows/ci.yml": workflow(permissions=True)}), "CI-PERMISSIONS"), "pass")

    def test_job_level_permissions_are_accepted(self):
        wf = workflow(permissions=False).replace("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    permissions:\n      contents: read\n")
        self.assertEqual(status(scan({".github/workflows/ci.yml": wf}), "CI-PERMISSIONS"), "pass")

    def test_write_all_permissions_rejected(self):
        wf = workflow(permissions=False).replace("jobs:", "permissions: write-all\n\njobs:")
        self.assertEqual(status(scan({".github/workflows/ci.yml": wf}), "CI-PERMISSIONS"), "fail")

    def test_timeouts(self):
        self.assertEqual(status(scan({".github/workflows/ci.yml": workflow(timeout=False)}), "CI-TIMEOUTS"), "fail")
        self.assertEqual(status(scan({".github/workflows/ci.yml": workflow()}), "CI-TIMEOUTS"), "pass")

    def test_aggregate_gate_detection(self):
        multi = workflow("  lint:\n    runs-on: ubuntu-latest\n    steps:\n      - run: make lint\n")
        self.assertEqual(status(scan({".github/workflows/ci.yml": multi}), "CI-GATE"), "fail")
        gated = multi + "  ci-success:\n    needs: [test, lint]\n    if: always()\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n"
        self.assertEqual(status(scan({".github/workflows/ci.yml": gated}), "CI-GATE"), "pass")
        no_always = gated.replace("    if: always()\n", "")
        self.assertEqual(status(scan({".github/workflows/ci.yml": no_always}), "CI-GATE"), "partial")

    def test_no_pr_trigger_is_not_a_pr_gate(self):
        wf = workflow().replace("  pull_request:\n", "")
        self.assertEqual(status(scan({".github/workflows/ci.yml": wf}), "CI-PR-TRIGGER"), "partial")

    def test_ci_detects_lint_test_build_through_the_task_runner(self):
        files = {".github/workflows/ci.yml": workflow(), "Makefile": "lint:\n\truff check .\ntest:\n\tpytest\nbuild:\n\tpython -m build\n"}
        report = scan(files)
        self.assertEqual(status(report, "CI-TEST"), "pass")
        self.assertEqual(status(report, "CI-LINT"), "pass")  # `make test` in CI reaches ruff via the Makefile
        report = scan({"Makefile": "test:\n\tpytest\n"})
        self.assertEqual(status(report, "CI-TEST"), "fail")  # no CI at all


class ContainerTests(unittest.TestCase):
    def dockerfile(self, text: str) -> dict:
        return {"Dockerfile": text, "app/main.py": "x=1\n", "pyproject.toml": '[project]\nname="a"\nversion="1"\n'}

    def test_user_and_pinning(self):
        bad = scan(self.dockerfile("FROM python:latest\nCOPY . .\nCMD [\"python\"]\n"))
        self.assertEqual(status(bad, "CTN-USER"), "fail")
        self.assertEqual(status(bad, "CTN-NO-LATEST"), "fail")
        self.assertIn("python:latest", evidence(bad, "CTN-NO-LATEST"))
        good = scan(self.dockerfile("FROM python:3.13-slim\nCOPY . .\nUSER 10001\nCMD [\"python\"]\n"))
        self.assertEqual(status(good, "CTN-USER"), "pass")
        self.assertEqual(status(good, "CTN-NO-LATEST"), "pass")

    def test_untagged_base_counts_as_latest(self):
        self.assertEqual(status(scan(self.dockerfile("FROM ubuntu\nUSER app\n")), "CTN-NO-LATEST"), "fail")

    def test_explicit_root_user_fails(self):
        self.assertEqual(status(scan(self.dockerfile("FROM alpine:3.20\nUSER root\n")), "CTN-USER"), "fail")

    def test_multistage_user_is_inherited_and_final_stage_decides(self):
        text = "FROM alpine:3.20 AS base\nUSER app\nFROM base AS final\nCMD [\"x\"]\n"
        self.assertEqual(status(scan(self.dockerfile(text)), "CTN-USER"), "pass")
        builder_only = "FROM golang:1.23 AS build\nUSER app\nFROM alpine:3.20\nCMD [\"x\"]\n"
        self.assertEqual(status(scan(self.dockerfile(builder_only)), "CTN-USER"), "fail")

    def test_known_nonroot_base_without_user_passes(self):
        self.assertEqual(status(scan(self.dockerfile("FROM gcr.io/distroless/static:nonroot\nCOPY a /a\n")), "CTN-USER"), "pass")

    def test_arg_driven_base_is_not_judged(self):
        text = "ARG BASE=python:3.13-slim\nFROM ${BASE}\nUSER 10001\n"
        self.assertEqual(status(scan(self.dockerfile(text)), "CTN-NO-LATEST"), "pass")

    def test_digest_pinning_and_multistage_and_dockerignore(self):
        digest = "b" * 64
        r = scan({**self.dockerfile(f"FROM python:3.13@sha256:{digest} AS b\nFROM python:3.13@sha256:{digest}\nUSER 1\n"), ".dockerignore": ".git\n"})
        self.assertEqual(status(r, "CTN-DIGEST"), "pass")
        self.assertEqual(status(r, "CTN-MULTISTAGE"), "pass")
        self.assertEqual(status(r, "CTN-DOCKERIGNORE"), "pass")
        r = scan(self.dockerfile("FROM python:3.13\nUSER 1\n"))
        self.assertEqual(status(r, "CTN-DIGEST"), "fail")
        self.assertEqual(status(r, "CTN-MULTISTAGE"), "fail")
        self.assertEqual(status(r, "CTN-DOCKERIGNORE"), "fail")

    def test_kubernetes_security_context_and_probes(self):
        weak = "apiVersion: apps/v1\nkind: Deployment\nspec:\n  template:\n    spec:\n      containers:\n        - name: a\n          image: a:1\n"
        strong = weak + "          readinessProbe: {}\n          livenessProbe: {}\n          resources:\n            limits: {}\n          securityContext:\n            runAsNonRoot: true\n            readOnlyRootFilesystem: true\n            allowPrivilegeEscalation: false\n"
        r = scan({"deploy/dep.yaml": weak})
        self.assertEqual(status(r, "CTN-K8S-PROBES"), "fail")
        self.assertEqual(status(r, "CTN-K8S-SECCTX"), "fail")
        r = scan({"deploy/dep.yaml": strong})
        self.assertEqual(status(r, "CTN-K8S-PROBES"), "pass")
        self.assertEqual(status(r, "CTN-K8S-RESOURCES"), "pass")
        self.assertEqual(status(r, "CTN-K8S-SECCTX"), "pass")


class SecretTests(unittest.TestCase):
    def test_committed_env_file_is_detected_without_leaking_the_value(self):
        r = scan({".env": "API_KEY=super-secret-value\n", ".env.example": "API_KEY=\n"})
        self.assertEqual(status(r, "SEC-NO-SECRETS"), "fail")
        self.assertIn(".env", evidence(r, "SEC-NO-SECRETS"))
        self.assertNotIn("super-secret-value", json.dumps(r))

    def test_env_example_alone_is_fine(self):
        self.assertEqual(status(scan({".env.example": "API_KEY=\n"}), "SEC-NO-SECRETS"), "pass")

    def test_private_key_block_detected(self):
        pem = "-----BEGIN " + "RSA PRIVATE KEY-----\n" + "MIIEowIBAAKCAQEA" + "x" * 60 + "\n-----END " + "RSA PRIVATE KEY-----\n"
        r = scan({"deploy/key.pem": pem})
        self.assertEqual(status(r, "SEC-NO-SECRETS"), "fail")
        self.assertNotIn("MIIEowIBAAKCAQEA", json.dumps(r))

    def test_prose_mentioning_private_keys_is_not_a_secret(self):
        r = scan({"src/ui.tsx": "const hint = '-----BEGIN " + "PRIVATE KEY-----';\n"})
        self.assertEqual(status(r, "SEC-NO-SECRETS"), "pass")

    def test_token_shape_detected_but_test_fixtures_are_softer(self):
        token = "AKIA" + "ABCDEFGHIJKLMNOP"
        self.assertEqual(status(scan({"config.py": f"KEY = '{token}'\n"}), "SEC-NO-SECRETS"), "fail")
        self.assertEqual(status(scan({"tests/test_cfg.py": f"KEY = '{token}'\n"}), "SEC-NO-SECRETS"), "partial")
        self.assertEqual(status(scan({"config.py": "KEY = 'AKIA" + "IOSFODNN7EXAMPLE'\n"}), "SEC-NO-SECRETS"), "pass")

    def test_env_gitignore_rule(self):
        self.assertEqual(status(scan({".gitignore": "node_modules/\n.env\n"}), "SEC-ENV-IGNORED"), "pass")
        self.assertEqual(status(scan({".gitignore": "node_modules/\n"}), "SEC-ENV-IGNORED"), "fail")

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_git_mode_ignores_untracked_ignored_files(self):
        with make_repo({".gitignore": ".env\n", ".env": "SECRET=1\n", "README.md": "# x\n"}) as root:
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            r = audit.run_audit(Repo(root, use_git=True))
            self.assertEqual(r["repo"]["listing"], "git")
            self.assertEqual(status(r, "SEC-NO-SECRETS"), "pass")
            r = audit.run_audit(Repo(root, use_git=False))
            self.assertEqual(status(r, "SEC-NO-SECRETS"), "fail")


class TestingChecksTests(unittest.TestCase):
    def test_tests_without_assertions_are_flagged(self):
        files = {"src/a.py": "x = 1\n", "tests/test_a.py": "def test_a():\n    pass\n", "tests/test_b.py": "def test_b():\n    x = 1\n"}
        r = scan(files)
        self.assertEqual(status(r, "TEST-ASSERT"), "fail")
        files["tests/test_a.py"] = "def test_a():\n    assert 1 == 1\n"
        files["tests/test_b.py"] = "def test_b():\n    assert 2 == 2\n"
        self.assertEqual(status(scan(files), "TEST-ASSERT"), "pass")

    def test_heavily_skipped_tests_are_not_a_pass(self):
        body = "import pytest\n\n" + "".join(f"@pytest.mark.skip\ndef test_{i}():\n    assert True\n\n" for i in range(5))
        self.assertNotEqual(status(scan({"src/a.py": "x=1\n", "tests/test_a.py": body}), "TEST-ASSERT"), "pass")

    def test_no_tests_fails_unit_check_and_helpers_are_not_tests(self):
        self.assertEqual(status(scan({"src/a.py": "x=1\n"}), "TEST-UNIT"), "fail")
        helpers_only = {"src/a.py": "x=1\n", "tests/conftest.py": "import pytest\n", "tests/helpers.py": "def h(): pass\n"}
        self.assertEqual(status(scan(helpers_only), "TEST-UNIT"), "fail")

    def test_ratio_thresholds(self):
        src = {f"src/m{i}.py": "x=1\n" for i in range(15)}
        one_test = {**src, "tests/test_one.py": "def test_x():\n    assert 1\n"}
        self.assertEqual(status(scan(one_test), "TEST-UNIT"), "partial")
        many = {**src, **{f"tests/test_{i}.py": "def test_x():\n    assert 1\n" for i in range(4)}}
        self.assertEqual(status(scan(many), "TEST-UNIT"), "pass")

    def test_coverage_threshold(self):
        base = {"src/a.py": "x=1\n", "tests/test_a.py": "def test_a():\n    assert 1\n"}
        self.assertEqual(status(scan(base), "TEST-COVERAGE"), "fail")
        self.assertEqual(status(scan({**base, "pyproject.toml": "[tool.coverage.run]\nsource=['a']\n"}), "TEST-COVERAGE"), "partial")
        self.assertEqual(status(scan({**base, "pyproject.toml": "[tool.coverage.report]\nfail_under = 80\n"}), "TEST-COVERAGE"), "pass")


class AgentChecksTests(unittest.TestCase):
    def test_agents_md_without_claude_bridge(self):
        r = scan({"AGENTS.md": "# a\n" + "word\n" * 20})
        self.assertEqual(status(r, "AGT-INSTRUCTIONS"), "pass")
        self.assertEqual(status(r, "AGT-CLAUDE-BRIDGE"), "fail")
        r = scan({"CLAUDE.md": "# only claude\n"})
        self.assertEqual(status(r, "AGT-INSTRUCTIONS"), "partial")
        self.assertEqual(status(r, "AGT-CLAUDE-BRIDGE"), "na")

    def test_invalid_skill_frontmatter_reported(self):
        files = {".agents/skills/foo/SKILL.md": "# no frontmatter\n", ".agents/skills/bar/SKILL.md": "---\nname: wrong\ndescription: Use when something happens and you need to do a long enough thing\n---\n"}
        r = scan(files)
        self.assertEqual(status(r, "AGT-SKILLS-VALID"), "fail")
        self.assertIn("foo", evidence(r, "AGT-SKILLS-VALID"))

    def test_deny_list_must_cover_env(self):
        weak = scan({".claude/settings.json": '{"permissions": {"allow": ["Bash(make *)"]}}'})
        self.assertEqual(status(weak, "AGT-PERMISSIONS"), "partial")

    def test_instruction_quality_signals(self):
        thin = scan({"AGENTS.md": "# Agents\n\nBe nice.\n" + "\n" * 20 + "more words\n" * 15})
        self.assertNotEqual(status(thin, "AGT-INSTR-QUALITY"), "pass")
        self.assertEqual(status(scan(good_repo_files()), "AGT-INSTR-QUALITY"), "pass")


class RobustnessTests(unittest.TestCase):
    STACKS = {
        "java": {"pom.xml": "<project><properties><maven.compiler.release>21</maven.compiler.release></properties>checkstyle</project>", "src/main/java/A.java": "class A{}", "src/test/java/ATest.java": "class ATest{ void t(){ assertEquals(1,1);} }"},
        "gradle": {"build.gradle.kts": "plugins{id(\"com.diffplug.spotless\")}\njvmToolchain(21)", "src/main/kotlin/A.kt": "fun a(){}", "gradle.lockfile": "x"},
        "rust": {"Cargo.toml": "[package]\nname='a'\nrust-version='1.80'\n", "src/main.rs": "fn main(){}", "tests/it.rs": "#[test] fn t(){ assert_eq!(1,1); }"},
        "ruby": {"Gemfile": "ruby '3.3'\ngem 'rails'\n", "Gemfile.lock": "x", "app.rb": "x=1", "spec/a_spec.rb": "expect(1).to eq(1)", ".rubocop.yml": "x: 1"},
        "php": {"composer.json": '{"require":{"php":"^8.2"}}', "a.php": "<?php", "tests/ATest.php": "<?php $this->assertTrue(1);"},
        "dotnet": {"a.csproj": "<Project><PropertyGroup><AnalysisLevel>8</AnalysisLevel></PropertyGroup></Project>", "P.cs": "class P{}", "global.json": "{}"},
        "node": {"package.json": '{"name":"a","dependencies":{"express":"4"},"scripts":{"test":"echo no test specified"}}', "index.js": "x=1", "index.test.js": "it('x',()=>{expect(1).toBe(1)})"},
        "monorepo": {"a/pyproject.toml": '[project]\nname="a"\nversion="1"\ndependencies=["x"]\n', "b/package.json": '{"dependencies":{"x":"1"}}', "b/index.ts": "x"},
        "helm": {"charts/app/Chart.yaml": "name: a", "charts/app/values.yaml": "resources: {limits: {}}", "charts/app/templates/d.yaml": "kind: Deployment\nspec:\n  containers:\n  - readinessProbe: {}\n"},
        "odd-workflow": {".github/workflows/a.yml": "on: [push]\njobs:\n  a:\n    uses: ./.github/workflows/b.yml\n  b:\n    needs:\n      - a\n    runs-on: x\n    steps:\n      - uses: docker://alpine\n"},
        "garbage": {"Dockerfile": "", "package.json": "{bad json", "pyproject.toml": "[[[", ".github/workflows/x.yml": "", "Makefile": "", "AGENTS.md": "\x00\x01"},
    }

    def test_no_check_crashes_on_any_stack_or_malformed_input(self):
        for name, files in self.STACKS.items():
            report = scan(files)
            errors = [(c["id"], c["evidence"]) for c in report["checks"] if "internal error" in c["evidence"]]
            self.assertEqual(errors, [], name)

    def test_language_specific_checks_recognise_other_stacks(self):
        self.assertEqual(status(scan(self.STACKS["java"]), "QUAL-LINT"), "pass")
        self.assertEqual(status(scan(self.STACKS["java"]), "DX-TOOLCHAIN"), "pass")
        self.assertEqual(status(scan(self.STACKS["rust"]), "TEST-UNIT"), "pass")
        self.assertEqual(status(scan(self.STACKS["ruby"]), "QUAL-LOCKFILES"), "pass")
        self.assertEqual(status(scan(self.STACKS["ruby"]), "QUAL-LINT"), "pass")
        self.assertEqual(status(scan(self.STACKS["node"]), "TEST-CONFIG"), "fail")  # npm's placeholder test script
        self.assertEqual(status(scan(self.STACKS["monorepo"]), "QUAL-LOCKFILES"), "fail")
        self.assertEqual(status(scan(self.STACKS["monorepo"]), "DOC-PKG-README"), "fail")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = make_repo({})
        self.addCleanup(self.tmp.cleanup)

    def test_min_score_exit_codes(self):
        below = run_cli(self.tmp.name, "--min-score", "50")
        self.assertEqual(below.returncode, 1)
        self.assertIn("below --min-score", below.stderr)
        self.assertEqual(run_cli(self.tmp.name, "--min-score", "0").returncode, 0)
        write_tree(self.tmp.name, good_repo_files())
        self.assertEqual(run_cli(self.tmp.name, "--min-score", "80", "--no-git").returncode, 0)

    def test_usage_errors_exit_2(self):
        self.assertEqual(run_cli("/definitely/not/a/dir").returncode, 2)
        bad = run_cli(self.tmp.name, "--category", "nonsense")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("unknown category", bad.stderr)

    def test_json_schema(self):
        write_tree(self.tmp.name, good_repo_files())
        proc = run_cli(self.tmp.name, "--format", "json", "--no-git")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["schema_version"], 1)
        for key in ("tool", "scope", "repo", "template_url", "score", "categories", "checks", "top_fixes", "quick_wins", "manual_review", "elapsed_seconds"):
            self.assertIn(key, data)
        self.assertEqual(set(data["score"]), {"overall", "grade", "checks"})
        self.assertEqual(set(data["score"]["checks"]), {"total", "applicable", "pass", "partial", "fail", "na"})
        self.assertEqual(set(data["repo"]), {"name", "path", "stacks", "flags", "files_scanned", "listing", "truncated"})
        self.assertEqual({c["id"] for c in data["categories"]}, {c.id for c in checks.CATEGORIES})
        for cat in data["categories"]:
            self.assertEqual(set(cat), {"id", "name", "weight", "applicable", "score", "grade", "rationale"})
        want = {"id", "category", "title", "weight", "effort", "status", "points", "evidence", "remediation", "template_refs", "gain"}
        for c in data["checks"]:
            self.assertEqual(set(c), want)
            self.assertIn(c["status"], ("pass", "partial", "fail", "na"))
            self.assertIn(c["effort"], ("S", "M", "L"))
            for ref in c["template_refs"]:
                self.assertTrue(ref["url"].startswith(data["template_url"]) and ref["url"].endswith(ref["path"]))
        counts = data["score"]["checks"]
        self.assertEqual(counts["total"], len(data["checks"]))
        self.assertEqual(counts["pass"] + counts["partial"] + counts["fail"] + counts["na"], counts["total"])

    def test_template_url_option_changes_links(self):
        proc = run_cli(self.tmp.name, "--format", "json", "--template-url", "https://example.invalid/t/blob/main/")
        data = json.loads(proc.stdout)
        self.assertEqual(data["template_url"], "https://example.invalid/t/blob/main")
        self.assertTrue(any(r["url"].startswith("https://example.invalid/t/blob/main/") for c in data["checks"] for r in c["template_refs"]))

    def test_category_filter_scopes_checks_and_score(self):
        proc = run_cli(self.tmp.name, "--format", "json", "--category", "security", "--category", "dx")
        data = json.loads(proc.stdout)
        self.assertEqual({c["category"] for c in data["checks"]}, {"security", "dx"})
        self.assertEqual({c["id"] for c in data["categories"]}, {"security", "dx"})
        self.assertEqual(data["scope"], "dx,security")
        by_name = json.loads(run_cli(self.tmp.name, "--format", "json", "--category", "Security & supply chain").stdout)
        self.assertEqual({c["category"] for c in by_name["checks"]}, {"security"})

    def test_markdown_and_text_reports(self):
        write_tree(self.tmp.name, {"README.md": "# x\n"})
        md = run_cli(self.tmp.name, "--format", "markdown").stdout
        for needle in ("# Repository audit:", "## Scorecard", "## Top fixes", "## Findings by category", "## Needs judgement", "| Documentation & onboarding |"):
            self.assertIn(needle, md)
        self.assertIn("/blob/main/", md)  # default template links
        txt = run_cli(self.tmp.name).stdout
        self.assertIn("Top fixes", txt)
        self.assertIn("grade F", txt)

    def test_list_checks(self):
        out = run_cli("--list-checks").stdout
        self.assertIn("CI-PINNED", out)
        self.assertEqual(len(out.strip().splitlines()), len(checks.all_checks()))


class RegistryIntegrityTests(unittest.TestCase):
    def test_rubric_catalogue_is_in_sync_with_the_registry(self):
        with open(os.path.join(SKILL_DIR, "references", "rubric.md"), encoding="utf-8") as fh:
            rubric = fh.read()
        start = rubric.index("<!-- BEGIN GENERATED CHECKS")
        body = rubric[rubric.index("\n", start) + 1:rubric.index("<!-- END GENERATED CHECKS -->")]
        self.assertEqual(body.strip(), audit.render_rubric().strip(), "regenerate: python3 scripts/audit.py --dump-rubric")

    def test_metadata_complete(self):
        for c in checks.all_checks():
            self.assertTrue(c.why and c.detect and c.remediation and c.template_ref, c.id)
            self.assertGreaterEqual(c.weight, 1)

    def test_template_refs_exist_when_run_inside_the_template(self):
        root = os.path.abspath(os.path.join(SKILL_DIR, "..", "..", ".."))
        if not os.path.isfile(os.path.join(root, ".github", "workflows", "ci.yml")):
            self.skipTest("not inside the template repository")
        missing = [(c.id, p) for c in checks.all_checks() for p in c.template_ref if not os.path.exists(os.path.join(root, p))]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
