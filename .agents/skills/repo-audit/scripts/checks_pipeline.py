"""Checks: CI/CD, code quality, testing."""

from __future__ import annotations

import os
import re

from registry import F, H, P, Result, check, from_reach, graded
from repo_context import SOURCE_EXT, Repo, Workflow
from checks_foundation import _langs

CI, QUALITY, TESTING = "ci", "quality", "testing"


def _gh_ci(r: Repo) -> bool:
    """GitHub-Actions-specific checks apply unless the repo clearly uses another CI system."""
    return bool(r.workflows()) or not r.other_ci()


GH_NA = "CI is not GitHub Actions"


def _pr_workflows(r: Repo) -> list[Workflow]:
    return [w for w in r.workflows() if w.triggers_pr]


# ======================================================================================================================
# CI/CD
# ======================================================================================================================
@check(
    "CI-EXISTS", CI, "CI is configured", 4, "S",
    why="Without automated checks every merge is a leap of faith, and agents get no signal that their change is safe.",
    detect="GitHub Actions workflows, GitLab CI, CircleCI, Jenkins, Azure Pipelines, Buildkite, Travis, Drone, etc.",
    fix="Add .github/workflows/ci.yml running lint, typecheck, test and build on pull requests.",
    ref=".github/workflows/ci.yml",
)
def _ci_exists(r: Repo) -> Result:
    f = r.ci_files()
    return P(f"{len(f)} CI file(s), e.g. {f[0]}") if f else F("no CI configuration found")


@check(
    "CI-PR-TRIGGER", CI, "Checks run on pull requests", 3, "S",
    why="Checks that only run after merge find problems too late; PR runs are the gate.",
    detect="A workflow triggered by pull_request or merge_group.",
    fix="Add `on: pull_request` (and `merge_group` if you use a merge queue) to the main CI workflow.",
    ref=".github/workflows/ci.yml",
    applies=_gh_ci, na=GH_NA,
)
def _ci_pr(r: Repo) -> Result:
    wf = r.workflows()
    if not wf:
        return F("no workflows")
    prs = _pr_workflows(r)
    return P(f"{len(prs)} workflow(s) run on PRs") if prs else H("workflows exist but none trigger on pull_request")


LINT_RX = r"\b(lint|ruff|flake8|pylint|eslint|biome|golangci|clippy|rubocop|checkstyle|pmd|spotbugs|phpstan|phpcs|shellcheck|pre-commit|mypy|pyright|tsc|detekt|ktlint|stylelint|prettier|black|gofmt|cargo fmt)\b"
TEST_RX = (
    r"\b(pytest|unittest|jest|vitest|mocha|playwright test|go test|cargo (nextest|test)|rspec|rake test|phpunit|dotnet test|"
    r"npm (run )?test|yarn test|pnpm (run )?test|tox|nox|bats|ctest|bun test|deno test)\b|\bmvn\b[^\n]*\b(test|verify)\b|"
    r"\bgradle[w]?\b[^\n]*\b(test|check)\b|\bmake\b[^\n]*\b(test|check)\b"
)
BUILD_RX = (
    r"\b(docker (buildx )?build|build-push-action|buildx|kaniko|npm (run )?build|yarn build|pnpm (run )?build|vite build|"
    r"cargo (build|check)|go (build|vet)|dotnet (build|publish)|python -m build|uv build|poetry build|helm package|tsc|next build)\b|"
    r"\bmvn\b[^\n]*\b(package|install|verify)\b|\bgradle[w]?\b[^\n]*\b(build|assemble)\b|\bmake\b[^\n]*\b(build|check|all)\b"
)


@check(
    "CI-LINT", CI, "CI runs lint/format/type checks", 2, "S",
    why="Style and type errors are cheapest to catch on every PR, mechanically, before a human reviews.",
    detect="Lint/format/typecheck commands (ruff, eslint, golangci-lint, clippy, mypy, tsc, make lint...) in CI text or in task-runner targets CI calls.",
    fix="Add a lint job that calls the same `make lint typecheck` developers run locally.",
    ref=(".github/workflows/ci.yml", "Makefile"),
)
def _ci_lint(r: Repo) -> Result:
    return from_reach(r.ci_reach(LINT_RX) if r.ci_files() else None, "lint/typecheck")


@check(
    "CI-TEST", CI, "CI runs the tests", 3, "S",
    why="A red/green test signal on every PR is the foundation of safe automated change.",
    detect="Test commands (pytest, jest, vitest, go test, cargo test, mvn test, make test...) in CI text or in task-runner targets CI calls.",
    fix="Add a test job calling `make test`; add integration/e2e jobs as they appear.",
    ref=(".github/workflows/ci.yml", "Makefile"),
)
def _ci_test(r: Repo) -> Result:
    return from_reach(r.ci_reach(TEST_RX) if r.ci_files() else None, "tests")


@check(
    "CI-BUILD", CI, "CI builds the artefact", 1, "S",
    why="Proves the code still compiles/bundles/containerises, not just that unit tests pass.",
    detect="Build commands (npm run build, go build, cargo build, docker build, mvn package, make build...) in CI or called task targets.",
    fix="Add a build job (and a container image build if you ship one).",
    ref=".github/workflows/ci.yml",
)
def _ci_build(r: Repo) -> Result:
    return from_reach(r.ci_reach(BUILD_RX) if r.ci_files() else None, "build")


GATE_NAME = re.compile(r"(?i)(success|gate|required|all[-_ ]?(checks?|green|pass(ed)?|jobs)|ci[-_ ]?(ok|pass)|alls-green|status[-_ ]?check|merge[-_ ]?ready)")


@check(
    "CI-GATE", CI, "Single aggregate required check", 3, "S",
    why="Branch protection should require ONE stable job; requiring individual jobs breaks as soon as path filters skip them or jobs are renamed.",
    detect="A PR-triggered workflow with a job named like success/gate/required that `needs:` 2+ jobs and runs `if: always()`. A workflow with a single job also passes.",
    fix="Add a `ci-success` job with `needs: [all jobs]`, `if: always()` and a step failing on failure/cancelled results; require only it.",
    ref=".github/workflows/ci.yml",
    applies=_gh_ci, na=GH_NA,
)
def _ci_gate(r: Repo) -> Result:
    prs = _pr_workflows(r)
    if not prs:
        return F("no PR workflow, so nothing to require")
    jobs = [j for w in prs for j in w.jobs]
    if len(jobs) <= 1:
        return P("a single job gates PRs")
    for w in prs:
        for j in w.jobs:
            named = GATE_NAME.search(j.id) or re.search(r"(?m)^\s+name:\s*(.+)$", j.text) and GATE_NAME.search(re.search(r"(?m)^\s+name:\s*(.+)$", j.text).group(1))
            if (named and len(j.needs) >= 2) or "alls-green" in j.text:
                if re.search(r"always\(\)|!cancelled\(\)|failure\(\)", j.text):
                    return P(f"{w.path}: job '{j.id}' aggregates {len(j.needs)} jobs with if: always()")
                return H(f"{w.path}: job '{j.id}' aggregates jobs but lacks `if: always()`, so skipped upstream jobs make it skip instead of pass/fail")
    return F(f"{len(jobs)} jobs run on PRs and none aggregates them; branch protection would have to list each one")


@check(
    "CI-CONCURRENCY", CI, "Stale runs are cancelled", 1, "S",
    why="Saves minutes and removes confusing results from superseded commits; essential when agents push often.",
    detect="The main PR workflow declares `concurrency:` with `cancel-in-progress`.",
    fix="Add `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}` (never cancel runs on the default branch).",
    ref=".github/workflows/ci.yml",
    applies=_gh_ci, na=GH_NA,
)
def _ci_conc(r: Repo) -> Result:
    prs = _pr_workflows(r)
    if not prs:
        return F("no PR workflow")
    main = max(prs, key=lambda w: len(w.jobs))
    if "concurrency:" in main.code and "cancel-in-progress" in main.code:
        return P(f"{main.path} cancels in-progress runs")
    return H(f"{main.path} has concurrency without cancel-in-progress") if "concurrency:" in main.code else F(f"{main.path} has no concurrency group")


@check(
    "CI-TIMEOUTS", CI, "Jobs have timeouts", 2, "S",
    why="A hung job otherwise burns six hours of runner time and blocks the queue; a timeout turns hangs into fast, visible failures.",
    detect="Share of workflow jobs (excluding reusable-workflow calls) with `timeout-minutes`.",
    fix="Add `timeout-minutes:` to every job (5-15 for most; longer only where justified).",
    ref=".github/workflows/ci.yml",
    applies=_gh_ci, na=GH_NA,
)
def _ci_timeouts(r: Repo) -> Result:
    jobs = [j for w in r.workflows() for j in w.jobs if not j.reusable]
    if not jobs:
        return F("no workflow jobs")
    ok = sum(1 for j in jobs if j.has_timeout)
    return graded(ok / jobs.__len__(), f"{ok}/{len(jobs)} jobs set timeout-minutes")


@check(
    "CI-PERMISSIONS", CI, "Least-privilege workflow permissions", 3, "S",
    why="The default GITHUB_TOKEN can write to the repo; a compromised or prompt-injected step then inherits that power.",
    detect="Every workflow has a top-level `permissions:` block (not write-all) or sets it on every job.",
    fix="Add `permissions: {}` at workflow level and grant `contents: read` (plus only what is needed) per job.",
    ref=".github/workflows/ci.yml",
    applies=_gh_ci, na=GH_NA,
)
def _ci_perms(r: Repo) -> Result:
    wfs = r.workflows()
    if not wfs:
        return F("no workflows")
    bad = []
    for w in wfs:
        top = w.top_permissions
        if top == "write-all":
            bad.append(f"{os.path.basename(w.path)} (write-all)")
        elif top is None and not (w.jobs and all(j.has_permissions for j in w.jobs)):
            bad.append(os.path.basename(w.path))
    return graded(1 - len(bad) / len(wfs), f"{len(wfs) - len(bad)}/{len(wfs)} workflows scope permissions" + (f"; missing: {', '.join(bad[:5])}" if bad else ""))


SHA = re.compile(r"^[0-9a-f]{40}$")


@check(
    "CI-PINNED", CI, "Actions pinned to commit SHAs", 3, "S",
    why="Tags are mutable: a hijacked action tag runs attacker code with your secrets. SHA pins (kept fresh by Dependabot) are immutable.",
    detect="Share of external `uses: owner/repo@ref` where ref is a 40-hex SHA (100% passes, 50%+ partial). Local and docker:// refs are ignored.",
    fix="Pin each action to its commit SHA with the version as a trailing comment; let Dependabot bump them.",
    ref=(".github/workflows/ci.yml", ".github/dependabot.yml"),
    applies=_gh_ci, na=GH_NA,
)
def _ci_pinned(r: Repo) -> Result:
    refs = [u for w in r.workflows() for u in w.uses() if not u.startswith(("./", "docker://"))]
    if not r.workflows():
        return F("no workflows")
    if not refs:
        return P("no external actions used")
    pinned = [u for u in refs if SHA.match(u.rpartition("@")[2])]
    loose = sorted({u for u in refs if u not in pinned})[:4]
    ratio = len(pinned) / len(refs)
    res = graded(ratio, f"{len(pinned)}/{len(refs)} action references pinned to a SHA" + (f"; e.g. {', '.join(loose)}" if loose else ""))
    return H(res.evidence) if 0 < ratio < 0.5 else res


@check(
    "CI-PATHS", CI, "Path filters in monorepo CI", 1, "M",
    why="Docs-only or single-package PRs should not pay for every package's pipeline; faster feedback keeps agents iterating.",
    detect="paths/paths-ignore on triggers or a changes-detection step (dorny/paths-filter, changed-files). Applies to repos with 2+ packages.",
    fix="Add a `changes` job (dorny/paths-filter + .github/changes-filter.yml) and gate package jobs on it; keep the aggregate gate.",
    ref=(".github/workflows/ci.yml", ".github/changes-filter.yml"),
    applies=lambda r: r.monorepo and _gh_ci(r), na="single-package repository or non-GitHub CI",
)
def _ci_paths(r: Repo) -> Result:
    text = "\n".join(w.code for w in r.workflows())
    if re.search(r"(?m)paths-filter|changed-files|^\s+paths(-ignore)?:|needs\.changes", text):
        return P("path/change filtering present")
    return F("monorepo CI runs everything on every PR")


@check(
    "CI-CACHE", CI, "Dependency caching", 1, "S",
    why="Caches cut CI time and reduce flaky downloads, which matters when many small agent PRs run CI.",
    detect="actions/cache, setup-* cache inputs, uv/rust cache, docker cache-from, GitLab cache:.",
    fix="Enable the cache option on setup-node/setup-python/setup-uv or add actions/cache keyed on the lockfile.",
    ref=".github/workflows/ci.yml",
)
def _ci_cache(r: Repo) -> Result:
    return P("dependency caching configured") if re.search(r"(?m)actions/cache|^\s*cache:\s|enable-cache|cache-from|rust-cache|cache-dependency|cache-to", r.ci_text()) else F("no dependency caching in CI")


@check(
    "CI-RELEASE", CI, "Release workflow", 2, "M",
    why="Repeatable releases (tag -> build -> publish -> notes) remove manual steps and 'what version is deployed?' questions.",
    detect="Workflow triggered by tags/release events, or release tooling (release-please, semantic-release, goreleaser, changesets, publish steps).",
    fix="Add a release workflow triggered on version tags that builds, publishes and creates release notes.",
    ref=(".github/release.yml", ".github/workflows/ci.yml"),
)
def _ci_release(r: Repo) -> Result:
    for w in r.workflows():
        if re.search(r"(?m)^\s*(tags|tags-ignore):|^\s*release:", w.header):
            return P(f"{w.path} triggers on tags/releases")
    m = re.search(r"release-please|semantic-release|goreleaser|changesets|gh release|action-gh-release|pypi-publish|twine upload|npm publish|cargo publish|helm push|docker push|push:\s*true", r.ci_text())
    return P(f"release/publish step: {m.group(0)}") if m else F("no release or publish automation")


@check(
    "CI-DEPLOY", CI, "Deployment is automated or verified in CI", 2, "L",
    why="Deploy steps that only exist in someone's shell history drift and break; a pipeline (or a cluster smoke test) keeps them honest.",
    detect="CI references helm/kubectl/terraform/cdk/fly/vercel/etc. deploys, kind/minikube smoke tests, or a deploy/cd workflow. Applies when containers or IaC exist.",
    fix="Add a deploy workflow (environment + approvals) and a kind-based smoke test that installs the chart.",
    ref=(".github/workflows/ci.yml", "scripts/kind-e2e.sh", "docs/deployment.md"),
    applies=lambda r: r.deploy_artifacts(), na="no deployable artefacts (Dockerfile, charts, IaC)",
)
def _ci_deploy(r: Repo) -> Result:
    rx = r"helm (upgrade|install)|kubectl (apply|set image|rollout)|(terraform|tofu) (apply|plan)|pulumi up|cdk deploy|sam deploy|serverless deploy|fly(ctl)? deploy|vercel|netlify|wrangler|gcloud (run|app) deploy|amazon-ecs-deploy|webapps-deploy|argocd app|kind (create|load)|kind-e2e|helm-lint|make (up|deploy)"
    if r.ci_reach(rx) in ("ci", "tasks"):
        return P("deploy or cluster smoke test runs in CI")
    if any(re.search(r"(?i)deploy|(^|[-_/])cd[-_.]", w.path) for w in r.workflows()):
        return P("deploy workflow present")
    return F("no deploy automation or cluster smoke test in CI")


@check(
    "CI-ACTIONLINT", CI, "Workflow files are linted", 1, "S",
    why="Workflow typos and unsafe expressions only fail at runtime; actionlint/zizmor catch them in seconds.",
    detect="actionlint, zizmor or check-github-workflows in CI or pre-commit.",
    fix="Run actionlint in CI (pinned, checksum-verified) and in pre-commit.",
    ref=(".github/workflows/ci.yml", "scripts/ci/install-tool.sh"),
    applies=lambda r: bool(r.workflows()), na="no GitHub workflows",
)
def _ci_actionlint(r: Repo) -> Result:
    return from_reach(r.ci_reach(r"actionlint|zizmor|check-github-workflows|action-validator"), "workflow linter")


@check(
    "CI-SCHEDULE", CI, "Scheduled run catches drift", 1, "S",
    why="New CVEs, deleted upstream tags and tool breakage appear without any commit; a weekly run surfaces them early.",
    detect="`schedule:` with a cron in any workflow.",
    fix="Add a weekly cron trigger to CI (full run, including slow jobs).",
    ref=".github/workflows/ci.yml",
    applies=_gh_ci, na=GH_NA,
)
def _ci_schedule(r: Repo) -> Result:
    hit = [w.path for w in r.workflows() if re.search(r"(?m)^\s*-?\s*cron:", w.header)]
    return P(f"cron in {hit[0]}") if hit else F("no scheduled workflow")


# ======================================================================================================================
# Code quality
# ======================================================================================================================
def _text_has(r: Repo, rx: str) -> bool:
    return bool(re.search(rx, r.tool_text() + "\n" + r.ci_text(), re.I))


def _agg(scores: dict[str, tuple[float, str]]) -> Result:
    mean = sum(s for s, _ in scores.values()) / len(scores)
    return graded(mean, "; ".join(f"{k}: {v[1]}" for k, v in scores.items()))


def _pyproject_text(r: Repo) -> str:
    return "\n".join(r.read(p) for p, _ in r.pyprojects())


def _lint_for(r: Repo, lang: str) -> tuple[float, str]:
    if lang == "python":
        t = _pyproject_text(r)
        if r.glob("**/ruff.toml", "**/.ruff.toml", "**/.flake8", "**/.pylintrc", "**/pylintrc") or re.search(r"\[tool\.(ruff|pylint|flake8)", t) or "[flake8]" in r.read("setup.cfg") + r.read("tox.ini"):
            return 1.0, "configured"
        return (1.0, "run via task runner/CI") if _text_has(r, r"\b(ruff check|flake8|pylint)\b") else (0.0, "no ruff/flake8/pylint")
    if lang == "js":
        if r.glob("**/eslint.config.*", "**/.eslintrc*", "**/biome.json", "**/biome.jsonc", "**/.oxlintrc.json", "**/deno.json") or any("eslintConfig" in d for _, d in r.package_jsons()):
            return 1.0, "eslint/biome configured"
        return 0.0, "no eslint/biome config"
    if lang == "go":
        if r.glob("**/.golangci.y*ml", "**/.golangci.toml", "**/.golangci.json"):
            return 1.0, "golangci-lint config"
        return (1.0, "go vet/staticcheck in tasks") if _text_has(r, r"golangci-lint|staticcheck|go vet") else (0.0, "no golangci-lint/staticcheck/vet")
    if lang == "rust":
        if r.glob("**/clippy.toml", "**/.clippy.toml") or _text_has(r, r"cargo clippy") or any("[lints" in r.read(p) for p in r.glob("**/Cargo.toml")):
            return 1.0, "clippy"
        return 0.0, "no clippy"
    if lang == "jvm":
        build = "\n".join(r.read(p) for p in r.glob("**/pom.xml", "**/build.gradle*"))
        if re.search(r"checkstyle|pmd|spotbugs|errorprone|detekt|ktlint|spotless|sonar", build, re.I) or r.glob("**/checkstyle*.xml", "**/detekt*.yml"):
            return 1.0, "static analysis plugin"
        return 0.0, "no checkstyle/pmd/spotbugs/detekt"
    if lang == "ruby":
        return (1.0, "rubocop") if r.glob("**/.rubocop.yml") else (0.0, "no .rubocop.yml")
    if lang == "php":
        return (1.0, "phpcs/phpstan") if r.glob("**/phpcs.xml*", "**/phpstan.neon*", "**/psalm.xml", "**/pint.json", "**/.php-cs-fixer*") else (0.0, "no phpcs/phpstan/pint")
    if lang == "dotnet":
        props = "\n".join(r.read(p) for p in r.glob("**/Directory.Build.props", "**/*.csproj"))
        if re.search(r"AnalysisLevel|AnalysisMode|EnableNETAnalyzers|StyleCop|Roslynator|TreatWarningsAsErrors", props):
            return 1.0, "analyzers enabled"
        return (0.5, ".editorconfig only") if r.has(".editorconfig") else (0.0, "no analyzers")
    return 0.0, "unsupported"


@check(
    "QUAL-LINT", QUALITY, "Linter configured per language", 4, "S",
    why="A linter encodes review feedback once, so humans stop repeating it and agents get immediate, local corrections.",
    detect="Per detected language: ruff/flake8/pylint, eslint/biome, golangci-lint/vet, clippy, checkstyle/spotbugs, rubocop, phpcs/phpstan, .NET analyzers.",
    fix="Add the standard linter config for each language and a `make lint` (check-only) target.",
    ref=("backend/pyproject.toml", "frontend/eslint.config.js"),
    applies=lambda r: bool(_langs(r)), na="no supported language detected",
)
def _q_lint(r: Repo) -> Result:
    return _agg({lang: _lint_for(r, lang) for lang in _langs(r)})


def _format_for(r: Repo, lang: str) -> tuple[float, str]:
    t = _pyproject_text(r)
    if lang == "python":
        if re.search(r"\[tool\.(black|yapf|autopep8)|\[tool\.ruff\.format", t) or _text_has(r, r"ruff format|\bblack\b|yapf|autopep8"):
            return 1.0, "formatter configured/run"
        return (0.5, "ruff config without a format step") if "[tool.ruff" in t else (0.0, "no formatter")
    if lang == "js":
        if r.glob("**/.prettierrc*", "**/prettier.config.*", "**/biome.json", "**/biome.jsonc", "**/dprint.json", "**/.dprint.json") or any("prettier" in d for _, d in r.package_jsons()):
            return 1.0, "prettier/biome"
        return 0.0, "no prettier/biome"
    if lang == "go":
        return (1.0, "gofmt enforced") if _text_has(r, r"gofmt|goimports|gofumpt|golangci-lint") else (0.5, "gofmt is built in but not enforced")
    if lang == "rust":
        return (1.0, "rustfmt") if r.glob("**/rustfmt.toml", "**/.rustfmt.toml") or _text_has(r, r"cargo fmt|rustfmt") else (0.5, "rustfmt not enforced")
    if lang == "jvm":
        build = "\n".join(r.read(p) for p in r.glob("**/pom.xml", "**/build.gradle*"))
        return (1.0, "formatter plugin") if re.search(r"spotless|google-java-format|ktfmt|scalafmt|ktlint|prettier-java", build, re.I) or r.glob("**/.scalafmt.conf") else (0.0, "no spotless/google-java-format")
    if lang == "ruby":
        return (1.0, "rubocop") if r.has(".rubocop.yml") else (0.0, "no rubocop")
    if lang == "php":
        return (1.0, "pint/cs-fixer") if r.glob("**/pint.json", "**/.php-cs-fixer*", "**/phpcs.xml*") else (0.0, "no php formatter")
    if lang == "dotnet":
        return (1.0, "dotnet format") if _text_has(r, r"dotnet format|csharpier") else ((0.5, ".editorconfig only") if r.has(".editorconfig") else (0.0, "no formatter"))
    return 0.0, "unsupported"


@check(
    "QUAL-FORMAT", QUALITY, "Formatter enforced per language", 3, "S",
    why="Automatic formatting ends style debates and keeps diffs (and agent edits) minimal.",
    detect="Per language: ruff format/black, prettier/biome, gofmt, rustfmt, spotless, rubocop, pint, dotnet format configured or run by tasks/CI.",
    fix="Add the formatter, a `make format` (writes) target and a check-only variant inside `make lint`.",
    ref=("backend/pyproject.toml", "frontend/.prettierrc.json"),
    applies=lambda r: bool(_langs(r)), na="no supported language detected",
)
def _q_format(r: Repo) -> Result:
    return _agg({lang: _format_for(r, lang) for lang in _langs(r)})


def _types_for(r: Repo, lang: str) -> tuple[float, str]:
    if lang == "python":
        t = _pyproject_text(r)
        if re.search(r"\[tool\.(mypy|pyright|pyre|ty)\b", t) or r.glob("**/mypy.ini", "**/.mypy.ini", "**/pyrightconfig.json", "**/.pyre_configuration") or "[mypy" in r.read("setup.cfg") + r.read("tox.ini") or _text_has(r, r"\b(mypy|pyright|pytype)\b"):
            return 1.0, "type checker configured"
        return 0.0, "no mypy/pyright"
    if lang == "js":
        ts = r.glob("**/tsconfig*.json")
        if ts:
            return (1.0, "tsconfig + tsc in tasks/CI") if _text_has(r, r"\btsc\b|vue-tsc|svelte-check|astro check") else (0.5, "tsconfig but no tsc/typecheck step")
        return (0.5, "jsconfig checkJs") if any("checkJs" in r.read(p) for p in r.glob("**/jsconfig.json")) else (0.0, "plain JavaScript, no type checking")
    if lang == "ruby":
        return (1.0, "sorbet/steep") if r.glob("**/sorbet/config", "**/Steepfile") else (0.0, "no sorbet/steep")
    if lang == "php":
        return (1.0, "phpstan/psalm") if r.glob("**/phpstan.neon*", "**/psalm.xml") else (0.0, "no phpstan/psalm")
    return 0.0, "n/a"


@check(
    "QUAL-TYPES", QUALITY, "Static type checking", 3, "M",
    why="Types turn whole classes of bugs into build failures and give agents precise feedback on interface mistakes.",
    detect="Python mypy/pyright config; TypeScript tsconfig plus a tsc step; Ruby sorbet/steep; PHP phpstan/psalm. Statically typed languages are excluded.",
    fix="Add mypy (or pyright) / tsc --noEmit and wire them into `make typecheck` and CI.",
    ref=("backend/pyproject.toml", "frontend/tsconfig.json"),
    applies=lambda r: any(lang in ("python", "js", "ruby", "php") for lang in _langs(r)), na="only statically typed languages detected",
)
def _q_types(r: Repo) -> Result:
    return _agg({lang: _types_for(r, lang) for lang in _langs(r) if lang in ("python", "js", "ruby", "php")})


def _strict_for(r: Repo, lang: str) -> tuple[float, str]:
    if lang == "python":
        t = _pyproject_text(r) + "\n".join(r.read(p) for p in r.glob("**/mypy.ini", "**/.mypy.ini", "**/pyrightconfig.json"))
        if re.search(r"\[tool\.mypy\][^\[]*?(strict\s*=\s*true|disallow_untyped_defs\s*=\s*true)|^strict\s*=\s*True|typeCheckingMode\W+strict|\[tool\.pyright\][^\[]*strict", t, re.I | re.S | re.M):
            return 1.0, "strict mode"
        return (0.5, "type checker without strict mode") if re.search(r"mypy|pyright", t) else (0.0, "no type checker")
    if lang == "js":
        cfgs = r.glob("**/tsconfig*.json")
        if any(re.search(r'"strict"\s*:\s*true', r.read(p)) for p in cfgs):
            return 1.0, "tsconfig strict: true"
        return (0.5, "tsconfig without strict (or inherits it)") if cfgs else (0.0, "no tsconfig")
    return 0.0, "n/a"


@check(
    "QUAL-STRICT", QUALITY, "Type checker runs in strict mode", 2, "M",
    why="Non-strict checking lets `Any` and untyped defs hide the bugs types exist to catch.",
    detect="Python: mypy strict/disallow_untyped_defs or pyright strict. TypeScript: `\"strict\": true` in a tsconfig.",
    fix="Enable `strict = true` (mypy) / `\"strict\": true` (tsconfig); fix or narrowly ignore the fallout.",
    ref=("backend/pyproject.toml", "frontend/tsconfig.json"),
    applies=lambda r: r.has_stack("python") or r.has_stack("typescript"), na="no Python or TypeScript",
)
def _q_strict(r: Repo) -> Result:
    langs = [lang for lang in _langs(r) if lang in ("python", "js") and (lang == "python" or r.has_stack("typescript"))]
    return _agg({lang: _strict_for(r, lang) for lang in langs})


@check(
    "QUAL-PRECOMMIT", QUALITY, "Pre-commit hooks", 2, "S",
    why="Catches formatting, secrets and lint errors before they reach CI; the same hooks can run in CI so local and remote agree.",
    detect=".pre-commit-config.yaml (3+ hooks passes), lefthook.yml, or husky + lint-staged.",
    fix="Add .pre-commit-config.yaml (whitespace, yaml/json checks, formatter, secret scan) and run it in CI.",
    ref=".pre-commit-config.yaml",
)
def _q_precommit(r: Repo) -> Result:
    if r.has(".pre-commit-config.yaml"):
        n = len(re.findall(r"(?m)^\s*-\s*id:", r.read(".pre-commit-config.yaml")))
        return P(f"{n} pre-commit hooks") if n >= 3 else H(f"only {n} pre-commit hook(s)")
    if r.glob("lefthook.y*ml", ".lefthook.y*ml"):
        return P("lefthook")
    if r.glob(".husky/*"):
        ls = bool(r.glob(".lintstagedrc*", "lint-staged.config.*")) or any("lint-staged" in d for _, d in r.package_jsons())
        return P("husky + lint-staged") if ls else H("husky hooks without lint-staged")
    return H(".githooks directory (not installed automatically)") if r.glob(".githooks/*") else F("no pre-commit framework")


@check(
    "QUAL-EDITORCONFIG", QUALITY, ".editorconfig", 1, "S",
    why="Gives every editor (and agent edit tool) the same indentation and newline rules.",
    detect=".editorconfig at repo root.",
    fix="Add .editorconfig with indent style/size, final newline and trailing-whitespace rules.",
    ref=".editorconfig",
)
def _q_editorconfig(r: Repo) -> Result:
    return P(".editorconfig") if r.has(".editorconfig") else F("no .editorconfig")


def _pyproject_has_deps(d: dict) -> bool:
    proj = d.get("project", {})
    return bool(proj.get("dependencies") or proj.get("optional-dependencies") or d.get("dependency-groups") or d.get("tool", {}).get("poetry", {}).get("dependencies"))


def _lock_for(r: Repo, eco: str, d: str) -> tuple[float, str] | None:
    """Score for one manifest directory, or None when it has nothing to lock."""
    def up(names: tuple[str, ...]) -> str | None:
        cur = d
        while True:
            for n in names:
                p = f"{cur}/{n}" if cur else n
                if r.has(p):
                    return p
            if not cur:
                return None
            cur = cur.rpartition("/")[0]

    label = d or "."
    if eco == "python":
        lock = up(("uv.lock", "poetry.lock", "Pipfile.lock", "pdm.lock", "pylock.toml", "requirements.lock"))
        if lock:
            return 1.0, f"{label}: {lock}"
        reqs = r.glob(f"{d + '/' if d else ''}requirements*.txt")
        reqs = [x for x in reqs if x.count("/") == d.count("/") + (1 if d else 0)]
        if reqs:
            lines = [ln.strip() for p in reqs for ln in r.read(p).splitlines() if ln.strip() and not ln.startswith(("#", "-"))]
            pinned = lines and all(re.search(r"==|@ |--hash", ln) for ln in lines)
            return (1.0, f"{label}: pinned requirements") if pinned else (0.0, f"{label}: unpinned requirements, no lockfile")
        pj = next((data for p, data in r.pyprojects() if os.path.dirname(p) == d), None)
        if pj is not None and not _pyproject_has_deps(pj):
            return None
        return (0.0, f"{label}: no lockfile") if pj is not None or r.has(f"{d}/setup.py" if d else "setup.py") else None
    if eco == "node":
        pkg = dict(r.package_jsons()).get(f"{d}/package.json" if d else "package.json", {})
        if not (pkg.get("dependencies") or pkg.get("devDependencies")):
            return None
        lock = up(("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb"))
        return (1.0, f"{label}: {lock}") if lock else (0.0, f"{label}: no lockfile")
    if eco == "go":
        return (1.0, f"{label}: go.sum") if up(("go.sum",)) or "require" not in r.read(f"{d}/go.mod" if d else "go.mod") else (0.0, f"{label}: go.sum missing")
    if eco == "rust":
        lock = up(("Cargo.lock",))
        return (1.0, f"{label}: Cargo.lock") if lock else (0.0, f"{label}: Cargo.lock not committed")
    if eco == "ruby":
        return (1.0, f"{label}: Gemfile.lock") if up(("Gemfile.lock",)) else (0.0, f"{label}: Gemfile.lock missing")
    if eco == "php":
        return (1.0, f"{label}: composer.lock") if up(("composer.lock",)) else (0.0, f"{label}: composer.lock missing")
    if eco == "jvm":
        if r.has(f"{d}/pom.xml" if d else "pom.xml"):
            return None  # Maven has no lockfile; version pinning is judged by review
        return (1.0, f"{label}: gradle.lockfile") if up(("gradle.lockfile",)) else (0.5, f"{label}: gradle dependency locking not enabled")
    if eco == "dotnet":
        return (1.0, f"{label}: packages.lock.json") if up(("packages.lock.json",)) else (0.5, f"{label}: NuGet lock files not enabled")
    return None


@check(
    "QUAL-LOCKFILES", QUALITY, "Dependency lockfiles committed", 3, "S",
    why="Reproducible installs: the same versions locally, in CI and in the image; also required for meaningful vulnerability scanning.",
    detect="Per manifest directory: uv.lock/poetry.lock/pinned requirements, package-lock/yarn/pnpm lock, go.sum, Cargo.lock, Gemfile.lock, composer.lock, gradle.lockfile. Maven is excluded.",
    fix="Generate and commit the lockfile (`uv lock`, `npm install --package-lock-only`, ...) and install with the frozen/`ci` variant in CI.",
    ref=("backend/uv.lock", "frontend/package-lock.json"),
    applies=lambda r: any(_lock_for(r, e, d) is not None for e, d in r.manifest_dirs()), na="no lockable manifests",
)
def _q_locks(r: Repo) -> Result:
    res = [x for e, d in r.manifest_dirs() if (x := _lock_for(r, e, d)) is not None]
    score = sum(s for s, _ in res) / len(res)
    bad = [m for s, m in res if s < 1]
    return graded(score, f"{len(res) - len(bad)}/{len(res)} manifests locked" + (f"; {'; '.join(bad[:4])}" if bad else ""))


@check(
    "QUAL-SHELLCHECK", QUALITY, "Shell scripts are linted", 1, "S",
    why="Shell fails silently in surprising ways; shellcheck catches quoting and portability bugs in scripts agents and CI rely on.",
    detect="shellcheck/shfmt in CI, task targets or pre-commit. Applies when .sh files exist.",
    fix="Run `shellcheck` over scripts/ in `make lint` (and a pre-commit hook).",
    ref=("Makefile", ".pre-commit-config.yaml"),
    applies=lambda r: bool(r.glob("**/*.sh")), na="no shell scripts",
)
def _q_shell(r: Repo) -> Result:
    return from_reach(r.ci_reach(r"shellcheck|shfmt|bashate"), "shellcheck")


# ======================================================================================================================
# Testing
# ======================================================================================================================
_TEST_NAME = re.compile(
    r"^(test_.*\.py|.*_test\.(py|go|rb|exs?)|.*\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs|mts|cts)|.*(Test|Tests|IT|Spec)\.(java|kt|scala|cs|groovy)|.*_spec\.rb|.*Test\.php|.*\.bats|.*_test\.rs)$"
)
_TEST_DIR = re.compile(r"(^|/)(tests?|__tests__|spec|specs)/")


def is_test_file(p: str) -> bool:
    b = os.path.basename(p)
    if _TEST_NAME.match(b):
        return True
    ext = os.path.splitext(b)[1].lower()
    if re.search(r"(^|/)__tests__/", p) and ext in (SOURCE_EXT["javascript"] | SOURCE_EXT["typescript"]) and not b.startswith("_"):
        return True
    if re.search(r"(^|/)tests?/", p) and ext == ".rs":
        return True  # Rust integration tests live in tests/*.rs
    return bool(re.search(r"(^|/)src/test/", p)) and ext in (SOURCE_EXT["jvm"] | {".cs"}) and not re.search(r"(?i)(^|/)src/test/resources/", p)


def _tests(r: Repo) -> list[str]:
    return r.memo("test_files", lambda: [f for f in r.files if is_test_file(f)])  # type: ignore[return-value]


def _source_count(r: Repo) -> int:
    code = set().union(*SOURCE_EXT.values())
    tests = set(_tests(r))
    return sum(
        1 for f in r.files
        if os.path.splitext(f)[1].lower() in code and f not in tests and not _TEST_DIR.search(f) and not re.search(r"\.d\.ts$|(^|/)(e2e|migrations|node_modules)/|\.config\.[cm]?[jt]s$|(^|/)(conftest|setup)\.py$", f)
    )


@check(
    "TEST-UNIT", TESTING, "Automated tests exist", 5, "M",
    why="Tests are the only objective definition of 'still works' for humans and agents alike; no tests means every change is unverified.",
    detect="Test files (test_*.py, *.test.ts, *_test.go, *Test.java, tests/, src/test ...) relative to source files: ratio >= 0.2 passes, >= 0.05 partial.",
    fix="Add unit tests for core logic first (pure functions, services), then API-level tests; keep them fast and offline.",
    ref=("backend/tests/unit/", "frontend/src/components/ItemsPage.test.tsx", "docs/testing.md"),
)
def _t_unit(r: Repo) -> Result:
    t, s = len(_tests(r)), _source_count(r)
    if not t:
        return F("no test files found")
    ratio = t / max(s, 1)
    ev = f"{t} test files for {s} source files (ratio {ratio:.2f})"
    return P(ev) if ratio >= 0.2 else H(ev) if ratio >= 0.05 else F(ev + "; far too thin to protect changes")


ASSERT_RX = re.compile(
    r"\bassert\b|\bexpect\s*[\(.]|\.should\b|\bt\.(Error|Fatal|Errorf|Fatalf)\b|\brequire\.|\bassert\.|assert_(eq|ne)!|assert!\(|\bAssert\.|assert(Equals|That|True|False|Null|Throws)\b|"
    r"\.to(Be|Equal|Have|Throw|Match|Contain|StrictEqual)\w*\(|\bpytest\.raises|\$this->assert|\bassert_equal\b|\bexpect_|\bshould\b|\bMust\b|\bis_expected\b|\bverify\("
)
TEST_FN_RX = re.compile(r"(?m)^\s*(async\s+)?def test_|\b(it|test)\s*\(\s*['\"`]|\bfunc Test\w+\(|@Test\b|#\[test\]|\b(it|specify)\s+['\"]|\[Fact\]|\[Theory\]")
SKIP_RX = re.compile(r"@pytest\.mark\.(skip|xfail)|pytest\.skip\(|\.skip\(|\bxit\(|\bxdescribe\(|\bxtest\(|@Ignore\b|@Disabled\b|\bt\.Skip|#\[ignore\]|\.todo\(|unittest\.skip|@unittest\.skip|\bpending\b")
FOCUS_RX = re.compile(r"\b(it|test|describe)\.only\(|\bfit\(|\bfdescribe\(|\bfocus: true")


@check(
    "TEST-ASSERT", TESTING, "Tests assert behaviour", 3, "M",
    why="Tests without assertions (or mostly skipped) give false confidence: coverage numbers look fine while nothing is checked.",
    detect="Samples up to 80 test files: share containing assertions (90%+ passes), share of skipped/xfail tests (<10%), committed `.only`. This is a heuristic; review a few tests by hand.",
    fix="Make each test assert an observable outcome (return value, HTTP response, persisted state); delete or fix skipped tests.",
    ref=("backend/tests/unit/test_item_service.py", "docs/testing.md"),
    applies=lambda r: bool(_tests(r)), na="no tests to inspect",
)
def _t_assert(r: Repo) -> Result:
    files = [f for f in _tests(r) if not f.endswith((".bats",))]
    step = max(1, len(files) // 80)
    sample = files[::step][:80]
    if not sample:
        return H("only shell/bats tests found; cannot assess assertions")
    with_assert, tests, skips, focus, empty = 0, 0, 0, 0, []
    for f in sample:
        t = r.read(f, 200_000)
        if ASSERT_RX.search(t):
            with_assert += 1
        else:
            empty.append(f)
        tests += len(TEST_FN_RX.findall(t))
        skips += len(SKIP_RX.findall(t))
        focus += len(FOCUS_RX.findall(t))
    a = with_assert / len(sample)
    s = skips / max(tests, 1)
    ev = f"{with_assert}/{len(sample)} sampled test files contain assertions; {skips} skipped of ~{tests} tests ({s:.0%})"
    if focus:
        return H(ev + f"; {focus} committed .only/focus markers")
    if empty:
        ev += f"; no assertions in e.g. {', '.join(empty[:3])}"
    if a >= 0.9 and s < 0.1:
        return P(ev)
    return H(ev) if a >= 0.6 and s < 0.25 else F(ev)


_INTEG_DIR = re.compile(r"(^|/)(integration|integ|itests?|integration[-_]tests?|integrationTest)(/|$)", re.I)


def _integration_files(r: Repo) -> list[str]:
    tests = set(_tests(r))
    code = set().union(*SOURCE_EXT.values())
    out = []
    for f in r.files:
        named = re.search(r"(?i)integration|_it\.|IT\.java$", os.path.basename(f))
        if f in tests and (_INTEG_DIR.search(f) or named):
            out.append(f)
        elif _INTEG_DIR.search(f) and os.path.splitext(f)[1].lower() in code and not re.search(r"(^|/)(conftest|__init__)\.py$", f):
            out.append(f)
    return out


def _integration_markers(r: Repo) -> bool:
    return _text_has(r, r"test-integration|integration-test|itest|testcontainers|-m integration|-tags=?integration|failsafe|integrationTest") or any(re.search(r"pytest\.mark\.integration|testcontainers|//go:build integration", r.read(f, 100_000)) for f in _tests(r)[:200])


@check(
    "TEST-INTEGRATION", TESTING, "Integration tests against real dependencies", 3, "M",
    why="Unit tests with mocks cannot catch schema, serialization and wiring bugs; integration tests against a real DB/service can.",
    detect="2+ test files in integration/ directories or named *integration*/*IT; markers (pytest mark, testcontainers, build tags, `test-integration` target) alone are partial.",
    fix="Add tests/integration/ that exercise the HTTP layer against a real database (compose or testcontainers) behind `make test-integration`.",
    ref=("backend/tests/integration/", "docs/testing.md"),
)
def _t_integration(r: Repo) -> Result:
    f = _integration_files(r)
    if len(f) >= 2:
        return P(f"{len(f)} integration test files")
    return H("integration markers/targets found but few or no dedicated test files") if f or _integration_markers(r) else F("no integration tests")


_E2E_FILES = ("**/playwright.config.*", "**/cypress.config.*", "cypress.json", "**/wdio.conf.*", "**/e2e/**", "**/*.e2e.*", "**/e2e_tests/**", "**/e2e-tests/**", "**/*.e2e-spec.*", "**/testcafe*", "**/.testcaferc*", "**/robot/**/*.robot", "**/*.robot", "**/k6/**", "**/hurl/**")


@check(
    "TEST-E2E", TESTING, "End-to-end tests", 2, "M",
    why="Only e2e tests prove the assembled system (UI to DB) works; they guard the user journeys that matter most.",
    detect="Playwright/Cypress/WebdriverIO/Selenium config plus spec files, or e2e directories. Config or specs alone are partial. Applies to services/apps.",
    fix="Add Playwright with a mocked-API project (fast, in CI) and a full-stack project against the compose stack.",
    ref=("frontend/playwright.config.ts", "frontend/e2e/"),
    applies=lambda r: r.is_service, na="not a service/application",
)
def _t_e2e(r: Repo) -> Result:
    files = r.glob(*_E2E_FILES)
    deps = r.node_deps()
    cfg_files = r.glob("**/playwright.config.*", "**/cypress.config.*", "**/wdio.conf.*")
    cfg = bool(cfg_files) or any(d in deps for d in ("@playwright/test", "playwright", "cypress", "selenium-webdriver", "puppeteer", "webdriverio", "testcafe"))
    roots = {os.path.dirname(c) for c in cfg_files}
    specs = [f for f in files if re.search(r"\.(spec|test|e2e|robot)\.|/e2e/|/e2e[-_]tests/", f) and not re.search(r"config\.", f)]
    specs += [
        f for f in r.files
        if f not in specs and re.search(r"\.(spec|cy)\.[cm]?[jt]sx?$", f) and any(f.startswith(d + "/") or not d for d in roots)
    ]
    if cfg and specs:
        return P(f"e2e framework configured with {len(specs)} spec files")
    if cfg or specs or _text_has(r, r"kind-e2e|e2e"):
        return H("partial e2e setup (" + ("config only" if cfg else "specs/targets without a framework config") + ")")
    return F("no end-to-end tests")


def _runner_ok(r: Repo, lang: str) -> tuple[float, str]:
    if lang == "python":
        t = _pyproject_text(r)
        if re.search(r"\[tool\.pytest|\[tool\.nose", t) or r.glob("**/pytest.ini", "**/conftest.py", "**/tox.ini", "**/noxfile.py") or "[tool:pytest]" in r.read("setup.cfg") or _text_has(r, r"unittest (discover|-m)|python3? -m unittest"):
            return 1.0, "pytest/unittest configured"
        return 0.5, "tests exist but no runner config; add pytest settings"
    if lang == "js":
        scripts = [d.get("scripts", {}).get("test", "") for _, d in r.package_jsons()]
        real = [s for s in scripts if s and "no test specified" not in s]
        if real or r.glob("**/jest.config.*", "**/vitest.config.*", "**/vitest.workspace.*"):
            return 1.0, "test script/config"
        return 0.0, "no real `test` script (npm placeholder)"
    return 1.0, "built-in toolchain runner"


@check(
    "TEST-CONFIG", TESTING, "Test runner configured and runnable by one command", 1, "S",
    why="A single documented command with fixed settings (paths, markers, env) makes test runs identical everywhere.",
    detect="Python: pytest/unittest config; JS: real `test` script or jest/vitest config; compiled languages use their built-in runner.",
    fix="Configure pytest/vitest in the package config and expose it as `make test`.",
    ref=("backend/pyproject.toml", "frontend/vite.config.ts"),
    applies=lambda r: bool(_tests(r)), na="no tests",
)
def _t_config(r: Repo) -> Result:
    langs: list[str] = []
    for f in _tests(r):
        ext = os.path.splitext(f)[1].lower()
        lang = "python" if ext == ".py" else "js" if ext in (SOURCE_EXT["javascript"] | SOURCE_EXT["typescript"]) else "other"
        if lang not in langs:
            langs.append(lang)
    return _agg({lang: _runner_ok(r, lang) for lang in langs})


def _has_slow_tests(r: Repo) -> bool:
    return len(_integration_files(r)) >= 1 or bool(r.glob(*_E2E_FILES[:6])) or _integration_markers(r)


@check(
    "TEST-CI-SLOW", TESTING, "Integration/e2e tests run in CI", 2, "M",
    why="Slow tests that only run on laptops rot; running them in CI keeps the expensive safety net alive.",
    detect="CI (or task targets it calls) invokes integration/e2e/playwright/cypress/testcontainers. Applies when such tests exist.",
    fix="Add CI jobs for `make test-integration` (service container) and `make test-e2e`; gate them in the aggregate check.",
    ref=".github/workflows/ci.yml",
    applies=_has_slow_tests, na="no integration/e2e tests",
)
def _t_ci_slow(r: Repo) -> Result:
    return from_reach(r.ci_reach(r"integration|e2e|playwright|cypress|wdio|testcontainers|webdriver|robot"), "integration/e2e tests") if r.ci_files() else F("no CI at all")


@check(
    "TEST-COVERAGE", TESTING, "Coverage measured with a threshold", 2, "S",
    why="Coverage is a floor, not a goal: a threshold stops silent erosion, and the report shows agents which code is untested.",
    detect="coverage/pytest-cov/c8/nyc/jacoco/tarpaulin/codecov config; a fail-under/threshold setting passes, measurement alone is partial.",
    fix="Enable coverage in the test target and set a fail-under ratchet (start at the current value).",
    ref=("backend/pyproject.toml", "frontend/vite.config.ts"),
    applies=lambda r: bool(_tests(r)), na="no tests",
)
def _t_cov(r: Repo) -> Result:
    cfg = "\n".join(r.read(p) for p in r.glob("**/.coveragerc", "**/codecov.y*ml", "**/.codecov.y*ml", "**/jest.config.*", "**/vitest.config.*", "**/vite.config.*", "**/.nycrc*", "**/tarpaulin.toml", "**/sonar-project.properties", "**/coveralls.y*ml"))
    blob = _pyproject_text(r) + cfg + "\n" + r.tool_text() + "\n" + r.ci_text()
    measured = re.search(r"\[tool\.coverage|pytest-cov|--cov\b|coverage run|\bc8\b|\bnyc\b|istanbul|--coverage|coverageThreshold|coverage:\s*\{|provider:\s*['\"](v8|istanbul)|codecov|coveralls|jacoco|tarpaulin|llvm-cov|-cover\b|simplecov|coverlet|sonar", blob, re.I)
    if not measured:
        return F("no coverage measurement")
    if re.search(r"fail_under|--cov-fail-under|coverageThreshold|thresholds?\s*[:=]|--fail-under|check-coverage|minimum\s*[>=]|target:\s*\d|jacoco[^\n]*minimum|--fail-under-line", blob, re.I):
        return P("coverage measured with an enforced threshold")
    return H("coverage is measured but no minimum is enforced")
