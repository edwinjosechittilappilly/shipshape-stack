"""Builders for throwaway fixture repositories used by the tests."""

from __future__ import annotations

import os
import tempfile

SHA = "a" * 40  # stands in for a pinned commit SHA


def write_tree(root: str, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)


def make_repo(files: dict[str, str] | None = None) -> tempfile.TemporaryDirectory:
    tmp = tempfile.TemporaryDirectory(prefix="repo-audit-test-")
    write_tree(tmp.name, files or {})
    return tmp


def workflow(body: str = "", *, pin: str = SHA, permissions: bool = True, timeout: bool = True) -> str:
    """A small single-job PR workflow; knobs flip one property at a time."""
    perms = "permissions:\n  contents: read\n\n" if permissions else ""
    tmo = "    timeout-minutes: 10\n" if timeout else ""
    return (
        "name: CI\n"
        "on:\n  pull_request:\n  push:\n    branches: [main]\n\n"
        f"{perms}"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        f"{tmo}"
        "    steps:\n"
        f"      - uses: actions/checkout@{pin}\n"
        "        with:\n          persist-credentials: false\n"
        "      - run: make test\n"
        f"{body}"
    )


def good_repo_files() -> dict[str, str]:
    """A small Python service that follows the practices the audit looks for (no frontend)."""
    readme = "# Svc\n\nA tiny service.\n\n## Quickstart\n\nPrerequisites: Python 3.13 and uv.\n\n```bash\nmake setup\nmake run\n```\n\n## Testing\n\n```bash\nmake test\n```\n\n" + "\n".join(f"Line {i} of useful documentation." for i in range(30)) + "\n"
    agents = (
        "# Agents\n\n## Commands\n\n- `make check` runs lint, typecheck and tests.\n- `make test` runs `pytest`.\n\n"
        "## Repo map\n\nThe layout is `src/` for code and `tests/` for tests; architecture lives in docs/.\n\n"
        "## Conventions\n\nFollow the code style enforced by ruff; keep formatting automatic.\n\n"
        "## Boundaries\n\nNever commit secrets. Do not edit generated files.\n\n"
        "## Verification\n\nBefore you open a pull request run `make check`; that is the definition of done.\n\n"
        "## Workflow\n\nUse conventional commit messages and one concern per branch and PR.\n" + "\n".join(f"- note {i}" for i in range(10)) + "\n"
    )

    def skill(name: str) -> str:
        return f"---\nname: {name}\ndescription: Use when you need to perform the {name} workflow in this repository and want the exact steps.\n---\n\n# {name}\n\nSteps.\n"

    labels = "".join(f'- name: "label {i}"\n  color: "ededed"\n' for i in range(11)) + '- name: "agent: ready"\n  color: "0e8a16"\n- name: "agent: review"\n  color: "0e8a16"\n'
    deps = (
        "version: 2\nupdates:\n"
        + "".join(f'  - package-ecosystem: "{e}"\n    directory: "/"\n    schedule:\n      interval: weekly\n' for e in ("pip", "github-actions", "docker", "terraform"))
    )
    ci = (
        "name: CI\n"
        "on:\n  pull_request:\n  merge_group:\n  push:\n    branches: [main]\n  schedule:\n    - cron: '17 4 * * 1'\n\n"
        "concurrency:\n  group: ci-${{ github.ref }}\n  cancel-in-progress: true\n\n"
        "permissions: {}\n\n"
        "jobs:\n"
        "  lint:\n    runs-on: ubuntu-latest\n    timeout-minutes: 10\n    permissions:\n      contents: read\n    steps:\n"
        f"      - uses: actions/checkout@{SHA} # v4\n        with:\n          persist-credentials: false\n"
        f"      - uses: astral-sh/setup-uv@{SHA} # v6\n        with:\n          enable-cache: true\n"
        "      - run: make lint\n      - run: actionlint\n"
        "  test:\n    runs-on: ubuntu-latest\n    timeout-minutes: 10\n    permissions:\n      contents: read\n    steps:\n"
        f"      - uses: actions/checkout@{SHA} # v4\n        with:\n          persist-credentials: false\n"
        "      - run: make test\n      - run: make test-integration\n"
        "  build:\n    runs-on: ubuntu-latest\n    timeout-minutes: 15\n    permissions:\n      contents: read\n    steps:\n"
        f"      - uses: actions/checkout@{SHA} # v4\n        with:\n          persist-credentials: false\n"
        "      - run: docker build -t svc:ci .\n      - run: make up\n"
        "  ci-success:\n    needs: [lint, test, build]\n    if: always()\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    permissions: {}\n    steps:\n"
        "      - run: test \"${{ contains(needs.*.result, 'failure') }}\" = false\n"
    )
    security = (
        "name: Security\non:\n  pull_request:\n  schedule:\n    - cron: '0 3 * * 2'\n\npermissions: {}\n\n"
        "jobs:\n  scan:\n    runs-on: ubuntu-latest\n    timeout-minutes: 15\n    permissions:\n      contents: read\n      security-events: write\n    steps:\n"
        f"      - uses: actions/checkout@{SHA} # v4\n        with:\n          persist-credentials: false\n"
        "      - run: trivy fs --config trivy.yaml .\n      - run: gitleaks detect --config .gitleaks.toml\n"
        f"      - uses: github/codeql-action/analyze@{SHA} # v3\n      - run: cosign verify image\n"
    )
    release = (
        "name: Release\non:\n  push:\n    tags: ['v*']\n\npermissions: {}\n\njobs:\n  publish:\n    runs-on: ubuntu-latest\n    timeout-minutes: 15\n"
        "    permissions:\n      contents: write\n    steps:\n"
        f"      - uses: actions/checkout@{SHA} # v4\n        with:\n          persist-credentials: false\n      - run: gh release create\n"
    )
    labeler = (
        "name: Label\non:\n  pull_request:\n\npermissions: {}\n\njobs:\n  label:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    permissions:\n      pull-requests: write\n    steps:\n"
        f"      - uses: actions/labeler@{SHA} # v5\n      - run: python scripts/ci/check_pr.py --title x\n"
    )
    return {
        "README.md": readme,
        "LICENSE": "Apache License\n",
        "CONTRIBUTING.md": "# Contributing\n" + "\n".join(f"Guideline {i}." for i in range(35)) + "\n",
        "CODE_OF_CONDUCT.md": "# Code of conduct\n",
        "CHANGELOG.md": "# Changelog\n",
        "SECURITY.md": "# Security\n\nReport vulnerabilities privately via the advisory form.\n" + "\n".join(f"Policy line {i}." for i in range(12)) + "\n",
        "docs/architecture.md": "# Architecture\n",
        "docs/testing.md": "# Testing\n",
        "docs/guide.md": "# Guide\n",
        "docs/adr/0000-template.md": "# ADR template\n",
        "docs/adr/0001-first.md": "# ADR 1\n",
        "docs/plans/README.md": "# Plans\n",
        "docs/plans/p1.md": "# Plan\n",
        "docs/agents/workflow.md": "# Agent workflow\n",
        "AGENTS.md": agents,
        "CLAUDE.md": "@AGENTS.md\n",
        ".agents/skills/pull-request/SKILL.md": skill("pull-request"),
        ".agents/skills/code-review/SKILL.md": skill("code-review"),
        ".agents/skills/ci-triage/SKILL.md": skill("ci-triage"),
        ".claude/settings.json": '{"permissions": {"allow": ["Bash(make *)"], "deny": ["Read(**/.env)"]}, "hooks": {"PreToolUse": [], "Stop": []}}',
        ".claude/commands/plan.md": "Plan it.\n",
        ".codex/hooks.json": '{"hooks": {"PreToolUse": []}}',
        ".coderabbit.yaml": "reviews:\n  profile: chill\n",
        ".github/ISSUE_TEMPLATE/task.yml": "name: Task\nbody:\n  - type: textarea\n    attributes:\n      label: Acceptance criteria\n  - type: checkboxes\n    attributes:\n      label: Agent ready\n",
        ".github/ISSUE_TEMPLATE/bug.yml": "name: Bug\nbody:\n  - type: textarea\n    attributes:\n      label: Steps\n",
        ".github/ISSUE_TEMPLATE/config.yml": "blank_issues_enabled: false\ncontact_links: []\n",
        ".github/pull_request_template.md": "## Summary\n\n## Changes\n\n## Verification\n\n## Checklist\n",
        ".github/labels.yml": labels,
        ".github/labeler.yml": "area: backend:\n  - changed-files:\n      - any-glob-to-any-file: src/**\n",
        ".github/release.yml": "changelog:\n  categories: []\n",
        ".github/CODEOWNERS": "* @owner\n",
        ".github/dependabot.yml": deps,
        ".github/workflows/ci.yml": ci,
        ".github/workflows/security.yml": security,
        ".github/workflows/release.yml": release,
        ".github/workflows/deploy.yml": workflow(),
        ".github/workflows/pr-labeler.yml": labeler,
        "pyproject.toml": '[project]\nname = "svc"\nversion = "0.1.0"\nrequires-python = ">=3.13"\ndependencies = ["fastapi"]\n\n[tool.ruff]\nline-length = 100\n\n[tool.ruff.format]\nquote-style = "double"\n\n[tool.mypy]\nstrict = true\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n\n[tool.coverage.report]\nfail_under = 80\n',
        "uv.lock": "version = 1\n",
        ".python-version": "3.13\n",
        "src/svc/__init__.py": "",
        "src/svc/core.py": "def add(a: int, b: int) -> int:\n    return a + b\n",
        "src/svc/web.py": "def health() -> dict[str, str]:\n    return {'status': 'ok'}\n",
        "tests/__init__.py": "",
        "tests/test_core.py": "from svc.core import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        "tests/test_web.py": "from svc.web import health\n\n\ndef test_health():\n    assert health() == {'status': 'ok'}\n",
        "tests/integration/__init__.py": "",
        "tests/integration/test_db.py": "def test_roundtrip():\n    assert True\n",
        "tests/integration/test_http.py": "def test_http():\n    assert 1 == 1\n",
        "tests/e2e/test_smoke.py": "def test_smoke():\n    assert True\n",
        "Makefile": ".PHONY: setup lint format test check build run\nsetup:\n\tuv sync\nlint:\n\truff check .\nformat:\n\truff format .\ntest:\n\tpytest\ncheck: lint test\nbuild:\n\tdocker build .\nrun:\n\tuvicorn svc.web:app\nup:\n\tdocker compose up -d\n",
        ".pre-commit-config.yaml": "repos:\n  - repo: https://example.invalid/hooks\n    rev: v1\n    hooks:\n      - id: end-of-file-fixer\n      - id: ruff\n      - id: gitleaks\n      - id: shellcheck\n",
        ".gitleaks.toml": "title = 'x'\n",
        "trivy.yaml": "severity: [HIGH]\n",
        ".editorconfig": "root = true\n",
        ".gitignore": ".env\n.env.*\n!.env.example\n__pycache__/\n.venv/\n",
        ".gitattributes": "* text=auto\n*.sh text eol=lf\n",
        ".env.example": "DATABASE_URL=postgresql://app:app@localhost/app\n",
        "Dockerfile": f"FROM python:3.13-slim@sha256:{'b' * 64} AS build\nWORKDIR /src\nCOPY . .\nRUN pip install .\nFROM python:3.13-slim@sha256:{'b' * 64}\nCOPY --from=build /src /app\nUSER 10001:10001\nCMD [\"python\", \"-m\", \"svc\"]\n",
        ".dockerignore": ".git\n.env*\n",
        "docker-compose.yml": "services:\n  db:\n    image: postgres:17\n    healthcheck:\n      test: [CMD, pg_isready]\n",
        "fly.toml": "app = 'svc'\n",
        "infra/main.tf": "terraform {}\n",
        "infra/.terraform.lock.hcl": "# lock\n",
        "scripts/run.sh": "#!/usr/bin/env bash\nset -eu\n",
    }
