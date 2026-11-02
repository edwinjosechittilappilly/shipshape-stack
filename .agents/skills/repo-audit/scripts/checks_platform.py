"""Checks: security & supply chain, containers & deployment, frontend health."""

from __future__ import annotations

import os
import re

from registry import F, H, P, Result, check, from_reach, graded
from repo_context import Repo

SEC, CTN, FE = "security", "containers", "frontend"


def _gh_workflows(r: Repo) -> bool:
    return bool(r.workflows())


# ======================================================================================================================
# Security & supply chain
# ======================================================================================================================
SCANNER_RX = r"trivy|grype|snyk|osv-scanner|npm audit|pnpm audit|yarn audit|pip-audit|safety check|cargo[- ]audit|cargo deny|govulncheck|dependency-check|bundler-audit|anchore|dependency-review-action|docker scout|checkov"
SCANNER_CFG = (".trivyignore", "trivy.y*ml", ".snyk", "osv-scanner.toml", "**/deny.toml", ".grype.y*ml")


@check(
    "SEC-SCANNER", SEC, "Vulnerability scanner in CI", 3, "M",
    why="Known-vulnerable dependencies and base images are the most common real-world exposure; scanning on every PR plus a schedule finds them early.",
    detect="trivy, grype, snyk, osv-scanner, npm/pip/cargo audit, govulncheck, dependency-review in CI or the task targets CI calls; config files alone are partial.",
    fix="Add a security job running Trivy (fs + image + config) with a pinned version, severity gate and a documented ignore file.",
    ref=(".github/workflows/security.yml", "trivy.yaml", ".trivyignore", "scripts/security/trivy-scan.sh"),
)
def _sec_scanner(r: Repo) -> Result:
    res = from_reach(r.ci_reach(SCANNER_RX), "vulnerability scanner")
    if res.status == "fail" and r.glob(*SCANNER_CFG):
        return H("scanner config exists but CI does not run a scanner")
    return res


SECRET_RX = r"gitleaks|trufflehog|detect-secrets|git-secrets|secretlint|ggshield|gitguardian|talisman"


@check(
    "SEC-SECRETS", SEC, "Secret scanning", 3, "S",
    why="A leaked credential in git history is permanent; scanning before commit and in CI is the cheap prevention.",
    detect="gitleaks/trufflehog/detect-secrets etc. in CI, pre-commit, or a config file (.gitleaks.toml, .secrets.baseline). Two of the three signals pass, one is partial.",
    fix="Add a gitleaks pre-commit hook and CI step plus a .gitleaks.toml allowlist for test fixtures.",
    ref=(".gitleaks.toml", ".pre-commit-config.yaml", ".github/workflows/security.yml"),
)
def _sec_secrets(r: Repo) -> Result:
    sig = {
        "CI": bool(re.search(SECRET_RX, r.ci_text() + r.tool_text(), re.I)) and bool(r.ci_reach(SECRET_RX) in ("ci", "tasks")),
        "pre-commit": bool(re.search(SECRET_RX, r.read(".pre-commit-config.yaml") + r.read("lefthook.yml"), re.I)),
        "config": bool(r.glob(".gitleaks.toml", ".gitleaksignore", ".secrets.baseline", ".trufflehog*", ".secretlintrc*")),
    }
    n = sum(sig.values())
    ev = "signals: " + ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in sig.items())
    return P(ev) if n >= 2 else H(ev) if n == 1 else F("no secret scanning")


_ECO_MAP = {
    "python": {"pip", "uv", "poetry", "pipenv"}, "node": {"npm", "yarn", "pnpm", "bun"}, "go": {"gomod"}, "rust": {"cargo"},
    "jvm": {"maven", "gradle"}, "ruby": {"bundler"}, "php": {"composer"}, "dotnet": {"nuget"},
}


@check(
    "SEC-DEPBOT", SEC, "Automated dependency updates", 3, "S",
    why="Unpatched dependencies and stale action pins accumulate risk; bot PRs keep updates small, frequent and reviewable.",
    detect="dependabot.yml covering every detected ecosystem (plus docker and github-actions when used) or any Renovate config. Partial when ecosystems are missing.",
    fix="Add .github/dependabot.yml with weekly updates and grouped minor/patch PRs for each ecosystem.",
    ref=".github/dependabot.yml",
)
def _sec_depbot(r: Repo) -> Result:
    if r.glob("renovate.json*", ".renovaterc*", ".github/renovate.json*", ".gitlab/renovate.json*") or any("renovate" in d for _, d in r.package_jsons()):
        return P("Renovate configured")
    f = r.first(".github/dependabot.y*ml")
    if not f:
        return F("no Dependabot or Renovate configuration")
    have = set(re.findall(r"package-ecosystem:\s*['\"]?([\w-]+)", r.read(f)))
    stacks = {"python" if s == "python" else "node" if s in ("node", "typescript") else s for s in r.stacks}
    missing = [eco for eco, names in _ECO_MAP.items() if eco in stacks and not (have & names)]
    if r.dockerfiles() and not have & {"docker", "docker-compose"}:
        missing.append("docker")
    if r.workflows() and "github-actions" not in have:
        missing.append("github-actions")
    if r.glob("**/*.tf") and "terraform" not in have and "opentofu" not in have:
        missing.append("terraform")
    return P(f"{f} covers: {', '.join(sorted(have))}") if not missing else H(f"{f} does not cover: {', '.join(missing)}")


@check(
    "SEC-CODEOWNERS", SEC, "CODEOWNERS", 2, "S",
    why="Routes reviews to the right people automatically and lets branch protection require owner approval on sensitive paths.",
    detect="CODEOWNERS at root, .github/ or docs/ with at least one rule.",
    fix="Add .github/CODEOWNERS mapping paths (CI, infra, security) to teams.",
    ref=".github/CODEOWNERS",
)
def _sec_owners(r: Repo) -> Result:
    f = r.first(".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")
    if not f:
        return F("no CODEOWNERS")
    rules = [ln for ln in r.read(f).splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    return P(f"{f}: {len(rules)} rules") if rules else H(f"{f} contains no rules")


@check(
    "SEC-POLICY", SEC, "SECURITY.md vulnerability policy", 2, "S",
    why="Tells reporters where to send findings privately and tells maintainers/agents never to file vulnerabilities as public issues.",
    detect="SECURITY.md at root, .github/ or docs/ mentioning how to report (advisory/email/private).",
    fix="Add SECURITY.md: supported versions, private reporting channel, response expectations.",
    ref="SECURITY.md",
)
def _sec_policy(r: Repo) -> Result:
    f = r.first("SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md")
    if not f:
        return F("no SECURITY.md")
    t = r.read(f)
    return P(f) if re.search(r"(?i)report|disclos|advisor|@", t) and len(t.splitlines()) >= 10 else H(f"{f} is thin: add a private reporting channel")


@check(
    "SEC-ENV-IGNORED", SEC, ".env files are gitignored", 2, "S",
    why="The commonest secret leak is a committed .env; ignoring it by default removes the foot-gun (and keeps it out of agent context).",
    detect=".gitignore (any depth) has a rule for .env / .env.* / *.env.",
    fix="Add `.env`, `.env.*` and `!.env.example` to .gitignore.",
    ref=".gitignore",
)
def _sec_envignore(r: Repo) -> Result:
    for g in r.glob("**/.gitignore"):
        if re.search(r"(?m)^\s*(\*\*/)?/?(\.env(\*|\.\*|\.local|\.\*\.local)?|\*\.env)\s*$", r.read(g)):
            return P(f"{g} ignores .env files")
    return F("no .gitignore rule for .env files")


PRIV = "-----BEGIN " + "(?:RSA |EC |OPENSSH |DSA |PGP |ENCRYPTED )?" + "PRIVATE KEY"
TOKEN_PATTERNS = {
    "private key": re.compile(PRIV + r"(?: BLOCK)?-----(?:\r?\n|\\n)\s*(?:[A-Za-z0-9+/=-]+:[^\n]*\n\s*)*[A-Za-z0-9+/=]{40,}"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "Stripe live key": re.compile(r"\bsk_live_[0-9a-zA-Z]{20,}"),
}
ENV_HARD = re.compile(r"(^|/)\.env$|(^|/)\.env\.local$")
ENV_SOFT = re.compile(r"(^|/)\.env\.(production|prod|staging)(\.local)?$|(^|/)\.env\.[\w.-]*\.local$")
KEY_FILES = re.compile(r"(^|/)(id_rsa|id_dsa|id_ecdsa|id_ed25519|\.pypirc|\.netrc|credentials\.json|terraform\.tfstate(\.backup)?)$|\.(p12|pfx|jks|keystore)$")
TEXT_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".env", ".properties", ".sh", ".tf", ".tfvars", ".xml", ".txt", ".md", ".pem", ".key", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs", ".gradle", ".cjs", ".mjs", ""}
SKIP_SCAN = re.compile(r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|uv\.lock|poetry\.lock|Cargo\.lock|go\.sum|composer\.lock|Gemfile\.lock|\.terraform\.lock\.hcl|__snapshots__)(/|$)|\.min\.|\.svg$")
FIXTURE_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|specs|fixtures?|testdata|__mocks__|mocks?|docs?|examples?)/|\.(test|spec)\.|_test\.|\.(md|rst|txt)$", re.I)


@check(
    "SEC-NO-SECRETS", SEC, "No committed secrets or private keys", 4, "S",
    why="Anything committed is public to every clone forever. This is the one finding that is an incident, not a todo.",
    detect="Static scan (no execution): committed .env/.env.local, private-key files and PEM blocks, cloud/Slack/GitHub/Stripe/Google token shapes, tfstate, .pypirc. .env.production/.staging only is partial. Paths are reported, never values.",
    fix="Remove the file, ROTATE the credential, purge history if needed, add the pattern to .gitignore and enable secret scanning.",
    ref=(".gitignore", ".gitleaks.toml", ".pre-commit-config.yaml"),
)
def _sec_no_secrets(r: Repo) -> Result:
    hard, soft = [], []
    for f in r.files:
        if ENV_HARD.search(f) or KEY_FILES.search(f):
            hard.append(f"{f} (secret-bearing file)")
        elif ENV_SOFT.search(f):
            soft.append(f"{f} (environment file)")
    scanned = 0
    for f in r.files:
        if scanned >= 4000:
            break
        if os.path.splitext(f)[1].lower() not in TEXT_EXT or SKIP_SCAN.search(f):
            continue
        try:
            if os.path.getsize(os.path.join(r.root, f)) > 200_000:
                continue
        except OSError:
            continue
        scanned += 1
        text = r.read(f, 200_000)
        for name, rx in TOKEN_PATTERNS.items():
            m = rx.search(text)
            if m and (name == "private key" or not re.search(r"EXAMPLE|XXXX", m.group(0), re.I)):
                fixture = name != "private key" and FIXTURE_PATH.search(f)
                (soft if fixture else hard).append(f"{f} ({name}{', likely a test fixture' if fixture else ''})")
                break
    if hard:
        return F("; ".join(hard[:6]) + (f"; +{len(hard) - 6} more" if len(hard) > 6 else ""))
    if soft:
        return H("; ".join(soft[:4]))
    return P(f"scanned {scanned} files and file names: none found")


@check(
    "SEC-SAST", SEC, "Static application security testing (SAST)", 2, "S",
    why="Finds injection, deserialisation and crypto misuse in first-party code that dependency scanners cannot see.",
    detect="CodeQL, semgrep, bandit, gosec, brakeman, SonarCloud/Qube, Snyk Code in CI; config only is partial. Repository-level 'default setup' of CodeQL cannot be seen statically.",
    fix="Add a codeql workflow (languages from your stack, weekly schedule) or semgrep with a pinned ruleset.",
    ref=".github/workflows/codeql.yml",
)
def _sec_sast(r: Repo) -> Result:
    rx = r"codeql|semgrep|bandit|sonar(cloud|qube|-scanner)|gosec|brakeman|njsscan|snyk code|horusec|checkmarx|veracode|codacy|deepsource"
    res = from_reach(r.ci_reach(rx), "SAST scanner")
    if res.status == "fail" and r.glob(".github/codeql/*", ".semgrep*", "sonar-project.properties", ".bandit"):
        return H("SAST config exists but CI does not run it")
    return res


@check(
    "SEC-IAC-SCAN", SEC, "Container/IaC misconfiguration scanning", 1, "S",
    why="Privileged containers, missing limits and open ports are caught as misconfigurations before deploy.",
    detect="trivy config/fs, checkov, kube-linter, kubeconform, hadolint, tfsec, conftest, helm lint in CI or tasks. Applies when Docker/Kubernetes/Terraform files exist.",
    fix="Run `trivy config`, hadolint and kubeconform (or checkov) on Dockerfiles, charts and IaC in CI.",
    ref=(".github/workflows/security.yml", "scripts/security/trivy-scan.sh"),
    applies=lambda r: r.deploy_artifacts(), na="no Dockerfile/Kubernetes/IaC files",
)
def _sec_iac(r: Repo) -> Result:
    return from_reach(r.ci_reach(r"trivy|checkov|tfsec|terrascan|kube-linter|kubeconform|kubeval|kube-score|hadolint|conftest|polaris|kics|dockle|helm[ -]lint|snyk iac"), "misconfiguration scanner")


def _checkout_steps(w) -> list[bool]:
    out, lines = [], w.code.splitlines()
    for i, ln in enumerate(lines):
        m = re.match(r"^(\s*)(-\s+)?uses:\s*actions/checkout\b", ln)
        if not m:
            continue
        col = len(m.group(1)) + (len(m.group(2)) if m.group(2) else 0)
        ok = False
        for nxt in lines[i + 1:i + 14]:
            if re.match(r"^\s*-\s", nxt) and len(nxt) - len(nxt.lstrip()) < col:
                break
            if re.search(r"persist-credentials:\s*false", nxt):
                ok = True
                break
        out.append(ok)
    return out


@check(
    "SEC-CHECKOUT", SEC, "Checkout does not persist credentials", 1, "S",
    why="`persist-credentials: false` stops later steps (or injected code) from reusing the token left in .git/config.",
    detect="Share of actions/checkout steps that set `persist-credentials: false`.",
    fix="Add `with: {persist-credentials: false}` to every checkout that does not push.",
    ref=".github/workflows/ci.yml",
    applies=lambda r: any(_checkout_steps(w) for w in r.workflows()), na="no checkout steps",
)
def _sec_checkout(r: Repo) -> Result:
    steps = [ok for w in r.workflows() for ok in _checkout_steps(w)]
    return graded(sum(steps) / len(steps), f"{sum(steps)}/{len(steps)} checkouts set persist-credentials: false")


@check(
    "SEC-PRT", SEC, "pull_request_target used safely", 2, "S",
    why="`pull_request_target` runs with write tokens and secrets; checking out the PR head there executes untrusted code with them.",
    detect="Flags workflows using pull_request_target that also check out the PR head (ref: github.event.pull_request.head.* / github.head_ref). Applies only when used.",
    fix="Use `pull_request` for untrusted code; if target is required, never check out or run PR-controlled code in it.",
    ref=".github/workflows/pr-labeler.yml",
    applies=lambda r: any("pull_request_target" in w.header for w in r.workflows()), na="pull_request_target not used",
)
def _sec_prt(r: Repo) -> Result:
    bad = [w.path for w in r.workflows() if "pull_request_target" in w.header and re.search(r"ref:\s*\$\{\{\s*github\.(event\.pull_request\.head|head_ref)", w.code)]
    return F(f"{', '.join(bad)} checks out PR-controlled code under pull_request_target") if bad else P("pull_request_target workflows do not check out the PR head")


@check(
    "SEC-PROVENANCE", SEC, "SBOM / signing / provenance", 1, "L",
    why="Lets consumers verify what was built from which commit and what is inside; increasingly required for enterprise adoption.",
    detect="syft/cyclonedx/spdx, cosign/sigstore, attest-build-provenance or SLSA generators in CI. Applies when images or a release workflow exist.",
    fix="Generate an SBOM and attach build provenance (`actions/attest-build-provenance`) or sign images with cosign in the release job.",
    ref=".github/workflows/ci.yml",
    applies=lambda r: bool(r.dockerfiles()) or bool(re.search(r"release|publish", r.ci_text(), re.I)), na="no images or release workflow",
)
def _sec_prov(r: Repo) -> Result:
    return from_reach(r.ci_reach(r"sbom|cosign|sigstore|attest|slsa|provenance|syft|cyclonedx|spdx"), "SBOM/signing/provenance step")


# ======================================================================================================================
# Containers & deployment
# ======================================================================================================================
NONROOT_BASE = re.compile(r"nonroot|unprivileged|distroless|cgr\.dev|chainguard|wolfi|rootless|bitnami/|/non-?root", re.I)


def _has_docker(r: Repo) -> bool:
    return bool(r.dockerfiles())


NO_DOCKER = "no Dockerfile"


@check(
    "CTN-DOCKERFILE", CTN, "Service is containerised", 2, "M",
    why="A Dockerfile is the portable, reviewable definition of how the service runs; it is the unit CI, scanners and clusters work with.",
    detect="Dockerfile/Containerfile anywhere in the repo. Applies to services/applications.",
    fix="Add a multi-stage Dockerfile per deployable (non-root, pinned base) and build it in CI.",
    ref=("backend/Dockerfile", "frontend/Dockerfile"),
    applies=lambda r: r.is_service, na="not a service/application",
)
def _ctn_dockerfile(r: Repo) -> Result:
    d = r.dockerfiles()
    return P(f"{len(d)} Dockerfile(s): {', '.join(x.path for x in d[:4])}") if d else F("no Dockerfile")


@check(
    "CTN-USER", CTN, "Images run as a non-root user", 4, "S",
    why="Root in the container turns any app compromise into a much easier node compromise; non-root is the single most valuable hardening step.",
    detect="Final build stage ends with a non-root USER (stage inheritance followed), or the base is a known non-root image (distroless:nonroot, *-unprivileged, chainguard).",
    fix="Create a numeric user (`USER 10001:10001`) in the final stage and make files readable by it.",
    ref=("backend/Dockerfile", "frontend/Dockerfile"),
    applies=_has_docker, na=NO_DOCKER,
)
def _ctn_user(r: Repo) -> Result:
    bad, ok = [], 0
    for d in r.dockerfiles():
        if not d.stages:
            continue
        user = d.effective_user()
        base = d.stages[-1].base
        if (user and user.lower() not in ("root", "0")) or (not user and NONROOT_BASE.search(base)):
            ok += 1
        else:
            bad.append(f"{d.path} ({'USER ' + user if user else 'no USER'})")
    total = ok + len(bad)
    return graded(ok / total, f"{ok}/{total} Dockerfiles end as non-root" + (f"; root: {', '.join(bad[:4])}" if bad else "")) if total else F("no parseable Dockerfile")


def _tag_state(base: str) -> str:
    if "$" in base:
        return "unknown"
    if "@sha256:" in base:
        return "digest"
    tail = base.rpartition("/")[2]
    if ":" not in tail:
        return "latest"
    return "latest" if tail.rpartition(":")[2] == "latest" else "tag"


@check(
    "CTN-NO-LATEST", CTN, "Base images pinned (no :latest)", 3, "S",
    why="`:latest` (or no tag) makes builds non-reproducible and lets a surprise upstream change break or compromise your image.",
    detect="Every external FROM has an explicit non-latest tag or digest. ARG-driven bases are skipped.",
    fix="Pin `FROM image:1.2.3` (or `@sha256:`), and let Dependabot's docker ecosystem bump them.",
    ref=("backend/Dockerfile", "frontend/Dockerfile", ".github/dependabot.yml"),
    applies=_has_docker, na=NO_DOCKER,
)
def _ctn_latest(r: Repo) -> Result:
    bases = [(d.path, b) for d in r.dockerfiles() for b in d.external_bases() if _tag_state(b) != "unknown"]
    if not bases:
        return P("no external base images to pin")
    bad = [f"{p}: {b}" for p, b in bases if _tag_state(b) == "latest"]
    return graded(1 - len(bad) / len(bases), f"{len(bases) - len(bad)}/{len(bases)} base images pinned" + (f"; floating: {', '.join(bad[:4])}" if bad else ""))


@check(
    "CTN-DIGEST", CTN, "Base images pinned by digest", 1, "M",
    why="Tags can be re-pointed; digests are immutable. Combined with a bot that bumps them, this is fully reproducible and safe.",
    detect="Share of external FROM lines containing @sha256:.",
    fix="Resolve each tag to a digest (`docker buildx imagetools inspect`) and write `image:tag@sha256:...`; let Dependabot update.",
    ref=("backend/Dockerfile", "frontend/Dockerfile"),
    applies=lambda r: any(d.external_bases() for d in r.dockerfiles()), na="no external base images",
)
def _ctn_digest(r: Repo) -> Result:
    bases = [b for d in r.dockerfiles() for b in d.external_bases() if "$" not in b]
    if not bases:
        return P("no external base images")
    n = sum("@sha256:" in b for b in bases)
    return graded(n / len(bases), f"{n}/{len(bases)} base images pinned by digest")


@check(
    "CTN-MULTISTAGE", CTN, "Multi-stage builds", 1, "S",
    why="Keeps compilers, caches and dev dependencies out of the runtime image: smaller, faster to pull, smaller attack surface.",
    detect="Share of Dockerfiles with 2+ FROM stages.",
    fix="Split into builder and runtime stages and COPY --from=builder only what runs.",
    ref=("backend/Dockerfile", "frontend/Dockerfile"),
    applies=_has_docker, na=NO_DOCKER,
)
def _ctn_multistage(r: Repo) -> Result:
    ds = r.dockerfiles()
    n = sum(len(d.stages) >= 2 for d in ds)
    return graded(n / len(ds), f"{n}/{len(ds)} Dockerfiles are multi-stage")


@check(
    "CTN-DOCKERIGNORE", CTN, ".dockerignore present", 2, "S",
    why="Without it the build context includes .git, node_modules and .env: slow builds, cache misses and leaked secrets in layers.",
    detect="A .dockerignore beside each Dockerfile or at the repo root.",
    fix="Add .dockerignore excluding .git, .env*, node_modules, .venv, tests and docs.",
    ref=("backend/.dockerignore", "frontend/.dockerignore"),
    applies=_has_docker, na=NO_DOCKER,
)
def _ctn_dockerignore(r: Repo) -> Result:
    ds = r.dockerfiles()
    missing = [d.path for d in ds if not (r.has(os.path.join(os.path.dirname(d.path), ".dockerignore").replace(os.sep, "/")) or r.has(".dockerignore") or r.has(d.path + ".dockerignore"))]
    return graded(1 - len(missing) / len(ds), f"{len(ds) - len(missing)}/{len(ds)} Dockerfiles have a .dockerignore" + (f"; missing for {', '.join(missing[:3])}" if missing else ""))


@check(
    "CTN-COMPOSE", CTN, "Local stack via Compose", 2, "S",
    why="`docker compose up` gives humans and agents a one-command, production-shaped environment (DB, migrations, app) for integration and e2e tests.",
    detect="docker-compose.yml / compose.yaml; healthchecks defined passes, bare file is partial.",
    fix="Add docker-compose.yml with the DB (healthcheck), a migration service and the app services.",
    ref="docker-compose.yml",
    applies=_has_docker, na=NO_DOCKER,
)
def _ctn_compose(r: Repo) -> Result:
    cf = r.compose_files()
    if not cf:
        return F("Dockerfiles exist but no Compose file for a local stack")
    return P(f"{cf[0]} with healthchecks") if any("healthcheck:" in r.read(f) for f in cf) else H(f"{cf[0]} has no healthchecks")


DEPLOY_DESCRIPTORS = ("**/kustomization.y*ml", "fly.toml", "render.yaml", "app.yaml", "serverless.yml", "vercel.json", "netlify.toml", "Procfile", "railway.json", "railway.toml", "cdk.json", "samconfig.toml", "appspec.yml", "**/Pulumi.yaml", "docker-stack.y*ml", "**/*.bicep", "**/*.tf", "**/*.nomad*", "app.json", "wrangler.toml", "skaffold.y*ml", "**/helmfile.y*ml")


@check(
    "CTN-DEPLOY-DESC", CTN, "Deployment is described as code", 3, "L",
    why="If the way to deploy lives only in someone's head, nobody (human or agent) can reproduce, review or roll it back.",
    detect="Helm chart, Kubernetes workload manifests, kustomize, Terraform/Pulumi/CDK/Bicep, or a platform descriptor (fly.toml, serverless.yml, vercel.json, ...). Applies to services.",
    fix="Add a Helm chart (or platform descriptor) under deploy/ with values, schema and a hook Job for migrations.",
    ref=("deploy/helm/app/", "docs/deployment.md"),
    applies=lambda r: r.is_service, na="not a service/application",
)
def _ctn_deploy(r: Repo) -> Result:
    hits = r.helm_charts() + r.k8s_workload_files() + r.glob(*DEPLOY_DESCRIPTORS)
    return P(f"{len(hits)} deployment descriptor file(s), e.g. {hits[0]}") if hits else F("no Helm/Kubernetes/IaC/platform deployment description")


def _chart_extra(r: Repo, path: str) -> str:
    cur = os.path.dirname(path)
    while True:
        if r.has(f"{cur}/Chart.yaml" if cur else "Chart.yaml"):
            return "\n".join(r.read(p) for p in r.glob(f"{cur}/values*.yaml" if cur else "values*.yaml"))
        if not cur:
            return ""
        cur = cur.rpartition("/")[0]


def _workload_scores(r: Repo, fn) -> tuple[float, str]:
    files = r.k8s_workload_files()
    scores = []
    for f in files:
        scores.append(fn(r.read(f, 200_000) + "\n" + _chart_extra(r, f)))
    mean = sum(scores) / len(scores)
    return mean, f"{sum(1 for s in scores if s >= 1)}/{len(scores)} workload files fully compliant"


_K8S = lambda r: bool(r.k8s_workload_files())  # noqa: E731


@check(
    "CTN-K8S-PROBES", CTN, "Kubernetes workloads define probes", 2, "S",
    why="Without liveness/readiness probes Kubernetes routes traffic to broken pods and never restarts hung ones.",
    detect="Workload manifests/Helm templates (and chart values) mention readinessProbe and livenessProbe/startupProbe.",
    fix="Add readiness + liveness probes pointing at cheap /readyz and /healthz endpoints.",
    ref=("deploy/helm/app/templates/backend-deployment.yaml",),
    applies=_K8S, na="no Kubernetes workloads",
)
def _ctn_probes(r: Repo) -> Result:
    def score(t: str) -> float:
        a, b = "readinessProbe" in t, bool(re.search(r"livenessProbe|startupProbe", t))
        return 1.0 if a and b else 0.5 if a or b else 0.0
    s, ev = _workload_scores(r, score)
    return graded(s, ev)


@check(
    "CTN-K8S-RESOURCES", CTN, "Kubernetes workloads set resource requests/limits", 2, "S",
    why="Unbounded pods starve neighbours and make scheduling and autoscaling unpredictable.",
    detect="`resources:` with requests/limits in manifests, templates or chart values.",
    fix="Set conservative requests and memory limits in values.yaml and reference them from every container.",
    ref=("deploy/helm/app/values.yaml",),
    applies=_K8S, na="no Kubernetes workloads",
)
def _ctn_resources(r: Repo) -> Result:
    s, ev = _workload_scores(r, lambda t: 1.0 if re.search(r"resources:", t) and re.search(r"requests|limits", t) else 0.0)
    return graded(s, ev)


@check(
    "CTN-K8S-SECCTX", CTN, "Kubernetes security context hardened", 3, "S",
    why="runAsNonRoot, read-only root filesystem, no privilege escalation and dropped capabilities contain a compromised container.",
    detect="Per workload (and chart values): 3+ of runAsNonRoot, readOnlyRootFilesystem, allowPrivilegeEscalation: false, capabilities drop ALL, seccompProfile passes; any securityContext is partial.",
    fix="Set the restricted pod-security profile fields in values.yaml and mount emptyDir for writable paths.",
    ref=("deploy/helm/app/values.yaml", "deploy/helm/app/templates/backend-deployment.yaml"),
    applies=_K8S, na="no Kubernetes workloads",
)
def _ctn_secctx(r: Repo) -> Result:
    keys = (r"runAsNonRoot", r"readOnlyRootFilesystem", r"allowPrivilegeEscalation", r"drop:|\bALL\b", r"seccompProfile")

    def score(t: str) -> float:
        n = sum(bool(re.search(k, t)) for k in keys)
        return 1.0 if n >= 3 else 0.5 if "securityContext" in t or n else 0.0
    s, ev = _workload_scores(r, score)
    return graded(s, ev)


@check(
    "CTN-IAC", CTN, "Infrastructure as code", 1, "L",
    why="Reviewable, repeatable infrastructure beats console clicks; lockfiles pin provider versions.",
    detect="Terraform/OpenTofu, Pulumi, CDK, Bicep or similar; Terraform without a committed .terraform.lock.hcl is partial.",
    fix="Describe the environment in Terraform/OpenTofu modules with committed lock files and a plan-in-CI job.",
    ref=("infra/terraform/",),
    applies=lambda r: r.is_service, na="not a service/application",
)
def _ctn_iac(r: Repo) -> Result:
    tf = r.terraform_files()
    if not tf:
        return F("no infrastructure-as-code files")
    if any(f.endswith((".tf", ".tofu")) for f in tf) and not r.glob("**/.terraform.lock.hcl"):
        return H("Terraform present but .terraform.lock.hcl is not committed")
    return P(f"{len(tf)} IaC file(s)")


@check(
    "CTN-HELM-LINT", CTN, "Helm charts are linted/validated in CI", 1, "S",
    why="Template errors and invalid manifests otherwise surface at deploy time.",
    detect="helm lint / helm template / kubeconform / chart-testing in CI or tasks. Applies when charts exist.",
    fix="Add `make helm-lint` (helm lint + helm template | kubeconform) and run it in CI.",
    ref=("Makefile", ".github/workflows/ci.yml"),
    applies=lambda r: bool(r.helm_charts()), na="no Helm charts",
)
def _ctn_helm(r: Repo) -> Result:
    return from_reach(r.ci_reach(r"helm[ -](lint|template|unittest)|kubeconform|chart-testing|\bct lint|kubeval"), "Helm validation")


# ======================================================================================================================
# Frontend health
# ======================================================================================================================
def _fe(r: Repo) -> bool:
    return r.frontend


FE_NA = "no JS UI framework detected"


@check(
    "FE-REACT-DOCTOR", FE, "React Doctor in scripts and CI", 3, "S",
    why="Surfaces dead code, unsafe effects, a11y and perf pitfalls in React code with one command; cheap to gate in CI and easy for agents to act on.",
    detect="`react-doctor` in package scripts/dependencies, a config file, or CI. Both script/config and CI passes; one is partial. Applies to React/Next apps.",
    fix="Add a `doctor` script (`npx react-doctor@latest .`), run it via a CI job (non-blocking at first), then ratchet.",
    ref=(".github/workflows/react-doctor.yml", "frontend/package.json"),
    applies=lambda r: r.react, na="no React app detected",
)
def _fe_doctor(r: Repo) -> Result:
    local = bool(re.search(r"react-doctor", r.tool_text() + " " + " ".join(r.node_deps()) + " ".join(r.glob("**/react-doctor.config.*")), re.I))
    ci = bool(re.search(r"react-doctor|make[^\n]*\bdoctor\b", r.ci_text(), re.I))
    return P("react-doctor configured locally and run in CI") if local and ci else H("react-doctor " + ("is configured but CI does not run it" if local else "runs in CI only; add a package script")) if local or ci else F("react-doctor not found")


@check(
    "FE-A11Y-LINT", FE, "Accessibility linting and tests", 3, "S",
    why="Accessibility bugs are invisible to unit tests; lint rules plus automated axe checks catch the majority at PR time.",
    detect="eslint-plugin-jsx-a11y (or vue/svelte/angular equivalents) AND an axe integration (@axe-core/playwright, jest-axe, vitest-axe) passes; one is partial.",
    fix="Add eslint-plugin-jsx-a11y to the ESLint config and an axe scan to the Playwright suite.",
    ref=("frontend/eslint.config.js", "frontend/e2e/a11y.mocked.spec.ts"),
    applies=_fe, na=FE_NA,
)
def _fe_a11y(r: Repo) -> Result:
    deps = " ".join(r.node_deps())
    lint = bool(re.search(r"jsx-a11y|vuejs-accessibility|angular-eslint|eslint-plugin-svelte|a11y", deps) or re.search(r"a11y", " ".join(r.read(p) for p in r.glob("**/eslint.config.*", "**/.eslintrc*", "**/biome.json*"))))
    axe = bool(re.search(r"axe-core|jest-axe|vitest-axe|pa11y|lighthouse", deps))
    ev = f"a11y lint: {'yes' if lint else 'no'}; axe/automated a11y tests: {'yes' if axe else 'no'}"
    return P(ev) if lint and axe else H(ev) if lint or axe else F("no accessibility tooling")


@check(
    "FE-PLAYWRIGHT", FE, "Browser e2e tests (Playwright)", 2, "M",
    why="Real-browser tests protect the user journeys; Playwright's accessible-name selectors also force an accessible UI.",
    detect="@playwright/test with a playwright.config; Cypress or another browser runner is partial.",
    fix="Add Playwright with `mocked` (stubbed API, CI-fast) and `fullstack` projects.",
    ref=("frontend/playwright.config.ts", "frontend/e2e/"),
    applies=_fe, na=FE_NA,
)
def _fe_pw(r: Repo) -> Result:
    deps = r.node_deps()
    if ("@playwright/test" in deps or "playwright" in deps) and r.glob("**/playwright.config.*"):
        return P("Playwright configured")
    return H("a non-Playwright browser runner is configured") if any(d in deps for d in ("cypress", "puppeteer", "webdriverio", "testcafe", "selenium-webdriver")) else F("no browser e2e runner")


@check(
    "FE-TS-STRICT", FE, "TypeScript strict mode", 3, "S",
    why="Strict TS catches null/undefined and implicit-any bugs at compile time and gives agents reliable type feedback across components.",
    detect="tsconfig with `\"strict\": true`; a tsconfig that only extends a shared base is partial; plain JS fails.",
    fix="Migrate to TypeScript and enable strict; use `// @ts-expect-error` narrowly while migrating.",
    ref="frontend/tsconfig.json",
    applies=_fe, na=FE_NA,
)
def _fe_ts(r: Repo) -> Result:
    cfgs = r.glob("**/tsconfig*.json")
    if any(re.search(r'"strict"\s*:\s*true', r.read(p)) for p in cfgs):
        return P("tsconfig strict: true")
    return H("tsconfig exists but strict mode is not enabled directly") if cfgs else F("frontend is not TypeScript")


@check(
    "FE-COMPONENT-TESTS", FE, "Component tests with Testing Library", 2, "S",
    why="Testing through roles and accessible names verifies behaviour users see and keeps tests stable across refactors.",
    detect="vitest or jest AND @testing-library/* in dependencies; one of them is partial.",
    fix="Add Vitest + @testing-library/react (jest-dom, user-event) and test components by role/name.",
    ref=("frontend/src/components/ItemsPage.test.tsx", "frontend/src/test/setup.ts"),
    applies=_fe, na=FE_NA,
)
def _fe_unit(r: Repo) -> Result:
    deps = r.node_deps()
    runner = any(d in deps for d in ("vitest", "jest", "@jest/core", "@web/test-runner"))
    lib = any(d.startswith("@testing-library/") for d in deps)
    ev = f"runner: {'yes' if runner else 'no'}; testing-library: {'yes' if lib else 'no'}"
    return P(ev) if runner and lib else H(ev) if runner or lib else F("no component test tooling")
