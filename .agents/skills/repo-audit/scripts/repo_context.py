"""Read-only view of a repository on disk, shared by every check.

Pure standard library. Nothing here executes target code or touches the network; files are only read
as text (size-capped) and the directory walk prunes dependency/build directories so large repos stay fast.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass, field
import subprocess

# Directories that never contain first-party source worth auditing (and are often huge).
SKIP_DIRS = frozenset(
    {
        ".git", "node_modules", ".venv", "venv", ".tox", ".nox", "__pycache__", ".mypy_cache", ".ruff_cache",
        ".pytest_cache", ".next", ".nuxt", ".svelte-kit", ".terraform", ".gradle", ".idea", ".vscode",
        "vendor", "dist", "build", "target", "coverage", "site-packages", "bower_components", ".cache",
        ".turbo", ".parcel-cache", ".eggs", "htmlcov", "playwright-report", "test-results",
        "storybook-static", ".direnv", ".cargo", "Pods",
    }
)
MAX_FILES = 150_000
MAX_DEPTH = 14
MAX_READ_BYTES = 512 * 1024

SOURCE_EXT = {
    "python": {".py"},
    "javascript": {".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte"},
    "typescript": {".ts", ".tsx", ".mts", ".cts"},
    "go": {".go"},
    "rust": {".rs"},
    "jvm": {".java", ".kt", ".kts", ".scala", ".groovy"},
    "ruby": {".rb"},
    "php": {".php"},
    "dotnet": {".cs", ".fs", ".vb"},
}

UI_FRAMEWORK_DEPS = (
    "react", "react-dom", "vue", "svelte", "@sveltejs/kit", "next", "nuxt", "@angular/core", "solid-js",
    "preact", "lit", "astro", "@remix-run/react", "@builder.io/qwik",
)
REACT_DEPS = ("react", "react-dom", "next", "preact", "@remix-run/react", "react-native")
WEB_SERVER_HINTS = re.compile(
    r"(?i)\b(fastapi|flask|django|starlette|aiohttp|tornado|sanic|litestar|uvicorn|gunicorn|express|fastify|koa|"
    r"@nestjs/core|hapi|hono|spring-boot|quarkus|micronaut|gin-gonic/gin|labstack/echo|gofiber/fiber|go-chi/chi|"
    r"gorilla/mux|actix-web|axum|rocket|rails|sinatra|laravel|symfony|aspnetcore)\b"
)

_GLOB_CACHE: dict[str, re.Pattern[str]] = {}


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a gitignore-ish glob (`**` crosses directories, `*` does not) into a regex."""
    if pattern in _GLOB_CACHE:
        return _GLOB_CACHE[pattern]
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    rx = re.compile("^" + "".join(out) + "$")
    _GLOB_CACHE[pattern] = rx
    return rx


def strip_comments(text: str) -> str:
    """Drop `#` comments (full-line and trailing) so keyword searches don't match prose."""
    out = []
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith("#"):
            continue
        out.append(re.sub(r"\s#.*$", "", line))
    return "\n".join(out)


# ----------------------------------------------------------------------------------------------------------------------
# GitHub Actions workflows (line-based: no YAML parser in the standard library)
# ----------------------------------------------------------------------------------------------------------------------
@dataclass
class Job:
    id: str
    lines: list[str]
    reusable: bool = False
    needs: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def has_timeout(self) -> bool:
        return bool(re.search(r"^\s+timeout-minutes:", self.text, re.M))

    @property
    def has_permissions(self) -> bool:
        return bool(re.search(r"^\s+permissions:", self.text, re.M))


@dataclass
class Workflow:
    path: str
    raw: str
    code: str  # comments stripped
    header: str  # everything before `jobs:`
    jobs: list[Job]

    @property
    def triggers_pr(self) -> bool:
        return bool(re.search(r"\b(pull_request|merge_group)\b", self.header))

    @property
    def top_permissions(self) -> str | None:
        m = re.search(r"^permissions:[ \t]*(.*)$", self.header, re.M)
        return None if not m else (m.group(1).strip() or "<block>")

    def uses(self) -> list[str]:
        return re.findall(r"^\s*-?\s*uses:\s*['\"]?([^\s#'\"]+)", self.code, re.M)


def parse_workflow(path: str, raw: str) -> Workflow:
    code = strip_comments(raw)
    m = re.search(r"^jobs:[ \t]*$", code, re.M)
    header = code[: m.start()] if m else code
    jobs: list[Job] = []
    if m:
        body = code[m.end():].splitlines()
        job_indent: int | None = None
        cur: Job | None = None
        for line in body:
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())
            if indent == 0:  # next top-level key ends the jobs block
                break
            if job_indent is None:
                job_indent = indent
            jm = re.match(r"^\s*([A-Za-z0-9_'\"-]+):\s*$", line)
            if indent == job_indent and jm:
                cur = Job(jm.group(1).strip("'\""), [])
                jobs.append(cur)
                continue
            if cur is not None:
                cur.lines.append(line)
        for j in jobs:
            j.reusable = bool(re.search(r"^\s{%d,%d}uses:" % ((job_indent or 2) + 2, (job_indent or 2) + 2), j.text, re.M))
            j.needs = _parse_needs(j.lines)
    return Workflow(path, raw, code, header, jobs)


def _parse_needs(lines: list[str]) -> list[str]:
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)needs:\s*(.*)$", line)
        if not m:
            continue
        rest = m.group(2).strip()
        if rest.startswith("["):
            return [x.strip(" '\"") for x in rest.strip("[]").split(",") if x.strip()]
        if rest:
            return [rest.strip("'\"")]
        out, base = [], len(m.group(1))
        for nxt in lines[i + 1:]:
            lm = re.match(r"^(\s*)-\s*(\S+)", nxt)
            if not lm or len(lm.group(1)) < base:
                break
            out.append(lm.group(2).strip("'\""))
        return out
    return []


# ----------------------------------------------------------------------------------------------------------------------
# Dockerfiles
# ----------------------------------------------------------------------------------------------------------------------
@dataclass
class Stage:
    base: str
    alias: str | None
    instructions: list[tuple[str, str]]  # (INSTRUCTION, args)

    def last(self, name: str) -> str | None:
        vals = [a for n, a in self.instructions if n == name]
        return vals[-1] if vals else None

    def has(self, name: str) -> bool:
        return any(n == name for n, _ in self.instructions)


@dataclass
class Dockerfile:
    path: str
    stages: list[Stage]

    def external_bases(self) -> list[str]:
        aliases = {s.alias for s in self.stages if s.alias}
        return [s.base for s in self.stages if s.base != "scratch" and s.base not in aliases]

    def effective_user(self, stage: Stage | None = None) -> str | None:
        """USER in effect at the end of `stage` (default: final stage), following stage inheritance."""
        stage = stage or (self.stages[-1] if self.stages else None)
        seen = 0
        while stage is not None and seen < 20:
            user = stage.last("USER")
            if user:
                return user.split(":")[0].strip()
            parent = next((s for s in self.stages if s.alias and s.alias == stage.base), None)
            stage, seen = parent, seen + 1
        return None


def parse_dockerfile(path: str, text: str) -> Dockerfile:
    joined = re.sub(r"\\\s*\n", " ", text)
    args: dict[str, str] = {}
    stages: list[Stage] = []
    for raw in joined.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        instr, rest = parts[0].upper(), (parts[1] if len(parts) > 1 else "")
        if instr == "ARG" and not stages:
            k, _, v = rest.partition("=")
            args[k.strip()] = v.strip().strip("'\"")
        elif instr == "FROM":
            toks = [t for t in rest.split() if not t.startswith("--")]
            base = toks[0] if toks else ""
            alias = toks[2] if len(toks) >= 3 and toks[1].lower() == "as" else None
            base = re.sub(
                r"\$\{(\w+)(?::?-([^}]*))?\}|\$(\w+)",
                lambda m: args.get(m.group(1) or m.group(3)) or m.group(2) or m.group(0),
                base,
            )
            stages.append(Stage(base, alias, []))
        elif stages:
            stages[-1].instructions.append((instr, rest))
    return Dockerfile(path, stages)


# ----------------------------------------------------------------------------------------------------------------------
# Repository
# ----------------------------------------------------------------------------------------------------------------------
CI_FILE_GLOBS = (
    ".github/workflows/*.yml", ".github/workflows/*.yaml", ".gitlab-ci.yml", ".gitlab/**/*.yml", "Jenkinsfile",
    ".circleci/config.yml", "azure-pipelines.yml", ".azure-pipelines/**/*.yml", ".buildkite/**/*.yml",
    ".travis.yml", ".drone.yml", ".woodpecker.yml", ".woodpecker/*.yml", "bitbucket-pipelines.yml", ".teamcity/**/*",
    "cloudbuild.yaml", "cloudbuild.yml", ".cirrus.yml", "buildspec.yml",
)
MANIFESTS = {
    "python": ("pyproject.toml", "setup.py", "setup.cfg", "Pipfile"),
    "node": ("package.json",),
    "go": ("go.mod",),
    "rust": ("Cargo.toml",),
    "jvm": ("pom.xml", "build.gradle", "build.gradle.kts"),
    "ruby": ("Gemfile",),
    "php": ("composer.json",),
    "dotnet": (),
}


class Repo:
    def __init__(self, root: str, use_git: bool = True):
        self.root = os.path.abspath(root)
        self.name = os.path.basename(self.root.rstrip(os.sep)) or self.root
        self.files: list[str] = []
        self.dirs: set[str] = set()
        self.truncated = False
        self.listing = "walk"
        if not (use_git and self._git_listing()):
            self._walk()
        self.fileset = set(self.files)
        self._text: dict[str, str] = {}
        self._cache: dict[str, object] = {}
        self.stacks = self._detect_stacks()

    # -- filesystem ---------------------------------------------------------------------------------------------------
    def _git_listing(self) -> bool:
        """Inside a git work tree, audit what git would commit: tracked + untracked-but-not-ignored files.

        This keeps local-only files (ignored .env, worktrees, caches) out of every check. Read-only `git ls-files`;
        returns False (caller falls back to a plain directory walk) when git is missing or the path is not a work tree.
        """
        try:
            proc = subprocess.run(
                ["git", "-c", "safe.directory=*", "-C", self.root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                capture_output=True, timeout=30, check=False, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
            )
        except (OSError, subprocess.SubprocessError):
            return False
        if proc.returncode != 0:
            return False
        seen: set[str] = set()
        for raw in proc.stdout.split(b"\0"):
            if not raw:
                continue
            rel = raw.decode("utf-8", errors="replace")
            parts = rel.split("/")
            if any(p in SKIP_DIRS for p in parts[:-1]) or len(parts) - 1 > MAX_DEPTH:
                continue
            full = os.path.join(self.root, rel)
            if rel in seen or os.path.isdir(full) and not os.path.islink(full):  # submodule / nested repo entries
                continue
            if not os.path.lexists(full):  # tracked but deleted in the work tree
                continue
            seen.add(rel)
            self.files.append(rel)
            for i in range(1, len(parts)):
                self.dirs.add("/".join(parts[:i]))
            if len(self.files) >= MAX_FILES:
                self.truncated = True
                break
        self.listing = "git"
        return True

    def _walk(self) -> None:
        base_depth = self.root.count(os.sep)
        for dirpath, dirnames, filenames in os.walk(self.root):
            rel_dir = os.path.relpath(dirpath, self.root).replace(os.sep, "/")
            depth = dirpath.count(os.sep) - base_depth
            keep = []
            for d in sorted(dirnames):
                full = os.path.join(dirpath, d)
                rel = d if rel_dir == "." else f"{rel_dir}/{d}"
                if d in SKIP_DIRS or rel == ".claude/worktrees":
                    continue
                self.dirs.add(rel)
                if os.path.islink(full):  # recorded (e.g. skills symlink) but never traversed
                    continue
                if depth + 1 <= MAX_DEPTH:
                    keep.append(d)
            dirnames[:] = keep
            for f in sorted(filenames):
                rel = f if rel_dir == "." else f"{rel_dir}/{f}"
                self.files.append(rel)
                if len(self.files) >= MAX_FILES:
                    self.truncated = True
                    return

    def has(self, path: str) -> bool:
        return path in self.fileset

    def has_dir(self, path: str) -> bool:
        return path.rstrip("/") in self.dirs or os.path.isdir(os.path.join(self.root, path))

    def glob(self, *patterns: str) -> list[str]:
        """Files matching any pattern, in listing order. Memoised; basename-only and literal patterns take fast paths."""
        key = "glob:" + "\0".join(patterns)
        if key in self._cache:
            return self._cache[key]  # type: ignore[return-value]
        literal = {p for p in patterns if not re.search(r"[*?]", p)}
        base = [p[3:] for p in patterns if p.startswith("**/") and "/" not in p[3:] and p not in literal]
        full = [p for p in patterns if p not in literal and not (p.startswith("**/") and "/" not in p[3:])]
        base_rx = re.compile("|".join(glob_to_regex(p).pattern for p in base)) if base else None
        full_rx = re.compile("|".join(glob_to_regex(p).pattern for p in full)) if full else None
        out = []
        for f in self.files:
            if f in literal or (full_rx and full_rx.match(f)) or (base_rx and base_rx.match(f.rpartition("/")[2])):
                out.append(f)
        self._cache[key] = out
        return out

    def first(self, *patterns: str) -> str | None:
        g = self.glob(*patterns)
        return g[0] if g else None

    def listdir(self, path: str) -> list[str]:
        try:
            return sorted(os.listdir(os.path.join(self.root, path)))
        except OSError:
            return []

    def is_symlink(self, path: str) -> bool:
        return os.path.islink(os.path.join(self.root, path))

    def read(self, path: str, limit: int = MAX_READ_BYTES) -> str:
        if path in self._text:
            return self._text[path]
        try:
            with open(os.path.join(self.root, path), "rb") as fh:
                data = fh.read(limit)
            text = data.decode("utf-8", errors="replace")
        except OSError:
            text = ""
        self._text[path] = text
        return text

    def read_code(self, path: str) -> str:
        return strip_comments(self.read(path))

    def count_ext(self, exts: set[str]) -> int:
        return sum(1 for f in self.files if os.path.splitext(f)[1].lower() in exts)

    def memo(self, key: str, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    # -- structured readers ---------------------------------------------------------------------------------------------
    def package_jsons(self) -> list[tuple[str, dict]]:
        def load():
            out = []
            for p in self.glob("**/package.json"):
                try:
                    data = json.loads(self.read(p))
                    if isinstance(data, dict):
                        out.append((p, data))
                except ValueError:
                    continue
            return out
        return self.memo("package_jsons", load)  # type: ignore[return-value]

    def node_deps(self) -> dict[str, str]:
        deps: dict[str, str] = {}
        for _, d in self.package_jsons():
            for k in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                if isinstance(d.get(k), dict):
                    deps.update(d[k])
        return deps

    def pyprojects(self) -> list[tuple[str, dict]]:
        def load():
            out = []
            for p in self.glob("**/pyproject.toml"):
                try:
                    out.append((p, tomllib.loads(self.read(p))))
                except (tomllib.TOMLDecodeError, ValueError):
                    out.append((p, {}))
            return out
        return self.memo("pyprojects", load)  # type: ignore[return-value]

    # -- stacks -------------------------------------------------------------------------------------------------------
    def _detect_stacks(self) -> list[str]:
        found: list[str] = []
        names = {os.path.basename(f) for f in self.files}
        for stack, manifests in MANIFESTS.items():
            if any(m in names for m in manifests):
                found.append(stack)
        if "python" not in found and (
            any(n.startswith("requirements") and n.endswith(".txt") for n in names) or self.count_ext({".py"}) >= 5
        ):
            found.append("python")
        if "dotnet" not in found and any(n.endswith((".csproj", ".fsproj", ".sln")) for n in names):
            found.append("dotnet")
        if "jvm" not in found and self.count_ext({".java", ".kt"}) >= 3:
            found.append("jvm")
        if "ruby" not in found and any(n.endswith(".gemspec") for n in names):
            found.append("ruby")
        # TypeScript is reported as its own stack on top of node.
        if "node" in found:
            if self.glob("**/tsconfig*.json") or "typescript" in self.node_deps() or self.count_ext(SOURCE_EXT["typescript"]):
                found.append("typescript")
            # A package.json alone (tooling-only repos) is not a JS codebase.
            if not self.count_ext(SOURCE_EXT["javascript"] | SOURCE_EXT["typescript"]) and not self.node_deps():
                found.remove("node")
                if "typescript" in found:
                    found.remove("typescript")
        elif self.count_ext(SOURCE_EXT["typescript"]) >= 3:
            found.append("typescript")
        return found

    def has_stack(self, *names: str) -> bool:
        return any(n in self.stacks for n in names)

    @property
    def js_like(self) -> bool:
        return self.has_stack("node", "typescript")

    @property
    def frontend(self) -> bool:
        return bool(self.memo("frontend", lambda: any(d in self.node_deps() for d in UI_FRAMEWORK_DEPS)))

    @property
    def react(self) -> bool:
        return bool(self.memo("react", lambda: any(d in self.node_deps() for d in REACT_DEPS)))

    def dockerfiles(self) -> list[Dockerfile]:
        def load():
            out = []
            for p in self.files:
                b = os.path.basename(p)
                if re.match(r"^(Dockerfile(\..+)?|.+\.Dockerfile|Containerfile(\..+)?)$", b):
                    if re.search(r"(^|/)(testdata|fixtures|examples?|\.devcontainer)/", p):
                        continue
                    out.append(parse_dockerfile(p, self.read(p)))
            return out
        return self.memo("dockerfiles", load)  # type: ignore[return-value]

    def compose_files(self) -> list[str]:
        return self.glob("**/docker-compose*.yml", "**/docker-compose*.yaml", "**/compose.yml", "**/compose.yaml")

    def k8s_workload_files(self) -> list[str]:
        """YAML files that define Kubernetes workloads (incl. Helm templates)."""
        def load():
            out, scanned = [], 0
            rx = re.compile(r"^\s*kind:\s*(Deployment|StatefulSet|DaemonSet|CronJob|ReplicaSet|Rollout)\b", re.M)
            for p in self.files:
                if not p.endswith((".yaml", ".yml", ".tpl")) or p.startswith(".github/"):
                    continue
                if "/node_modules/" in p or scanned >= 3000:
                    continue
                scanned += 1
                if rx.search(self.read(p, 200_000)):
                    out.append(p)
            return out
        return self.memo("k8s_workloads", load)  # type: ignore[return-value]

    def helm_charts(self) -> list[str]:
        return self.glob("**/Chart.yaml")

    def terraform_files(self) -> list[str]:
        return self.glob("**/*.tf", "**/*.tofu", "**/Pulumi.yaml", "**/cdk.json", "**/*.bicep", "**/serverless.yml")

    # -- CI / tooling text ----------------------------------------------------------------------------------------------
    def workflows(self) -> list[Workflow]:
        def load():
            return [
                parse_workflow(p, self.read(p)) for p in self.glob(".github/workflows/*.yml", ".github/workflows/*.yaml")
            ]
        return self.memo("workflows", load)  # type: ignore[return-value]

    def ci_files(self) -> list[str]:
        return self.memo("ci_files", lambda: self.glob(*CI_FILE_GLOBS))  # type: ignore[return-value]

    def ci_text(self) -> str:
        return self.memo("ci_text", lambda: "\n".join(self.read_code(p) for p in self.ci_files()))  # type: ignore[return-value]

    def other_ci(self) -> bool:
        return any(not p.startswith(".github/workflows/") for p in self.ci_files())

    def tool_files(self) -> list[str]:
        def find():
            fs = self.glob(
                "Makefile", "makefile", "GNUmakefile", "*/Makefile", "*/*/Makefile", "justfile", "Justfile",
                "Taskfile.yml", "Taskfile.yaml", ".pre-commit-config.yaml", "lefthook.yml", "tox.ini", "noxfile.py",
                "mise.toml", ".mise.toml", "scripts/**/*.sh", "scripts/**/*.py", "bin/*", ".husky/*", "package.json",
                "*/package.json", "*/*/package.json", "pyproject.toml", "*/pyproject.toml", "*/*/pyproject.toml",
                "ci/**/*.sh", "tools/**/*.sh", ".config/**/*.yml",
            )
            return fs
        return self.memo("tool_files", find)  # type: ignore[return-value]

    def tool_text(self) -> str:
        def build():
            chunks = []
            for p in self.tool_files():
                t = self.read(p, 200_000)
                if p.endswith("package.json"):
                    try:  # only scripts are task definitions; dependency names are matched separately
                        t = json.dumps(json.loads(t).get("scripts", {}))
                    except (ValueError, AttributeError):
                        pass
                chunks.append(strip_comments(t))
            return "\n".join(chunks)
        return self.memo("tool_text", build)  # type: ignore[return-value]

    def ci_invokes_tasks(self) -> bool:
        return bool(re.search(r"\b(make|just|task|tox|nox)\b |npm (run|test|ci)|pnpm |yarn |\./scripts/|scripts/|\./ci/", self.ci_text()))

    def ci_reach(self, pattern: str) -> str | None:
        """Where `pattern` shows up: 'ci' (workflow text), 'tasks' (task runner/scripts reachable from CI), 'config-only' or None."""
        rx = re.compile(pattern, re.I)
        if rx.search(self.ci_text()):
            return "ci"
        if rx.search(self.tool_text()):
            return "tasks" if self.ci_invokes_tasks() else "config-only"
        return None

    # -- derived facts ------------------------------------------------------------------------------------------------
    def manifest_dirs(self) -> list[tuple[str, str]]:
        """(ecosystem, directory) for every manifest, ignoring tooling-only package.json files."""
        def build():
            out = []
            for p in self.files:
                b = os.path.basename(p)
                d = os.path.dirname(p)
                if re.search(r"(^|/)(stubs?|fixtures?|examples?|samples?|testdata|__fixtures__|e2e|tests?)(/|$)", d):
                    continue  # throwaway packages inside fixtures/examples are not part of the product
                for eco, ms in MANIFESTS.items():
                    if b in ms and b not in ("setup.cfg",):
                        out.append((eco, d))
                if b.endswith((".csproj", ".fsproj")):
                    out.append(("dotnet", d))
                if re.match(r"^requirements[\w.-]*\.txt$", b) and not any(e == "python" and dd == d for e, dd in out):
                    out.append(("python", d))
            return sorted(set(out))
        return self.memo("manifest_dirs", build)  # type: ignore[return-value]

    @property
    def monorepo(self) -> bool:
        return len({d for _, d in self.manifest_dirs()}) >= 2

    @property
    def is_service(self) -> bool:
        def calc():
            if self.frontend or self.dockerfiles() or self.compose_files() or self.k8s_workload_files():
                return True
            blob = " ".join(self.node_deps())
            for p, data in self.pyprojects():
                blob += " " + json.dumps(data.get("project", {}).get("dependencies", []))
            for p in self.glob("**/requirements*.txt", "**/go.mod", "**/Cargo.toml", "**/pom.xml", "**/build.gradle*", "**/Gemfile", "**/composer.json"):
                blob += " " + self.read(p, 100_000)
            return bool(WEB_SERVER_HINTS.search(blob))
        return bool(self.memo("is_service", calc))

    def deploy_artifacts(self) -> bool:
        return bool(self.dockerfiles() or self.compose_files() or self.k8s_workload_files() or self.helm_charts() or self.terraform_files())
