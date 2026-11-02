# Security tooling and supply-chain rules

For reporting a vulnerability see [SECURITY.md](../SECURITY.md). This page documents what the repository scans automatically, how to handle findings, and the rules that keep CI itself from becoming the attack path.

## What runs where

| Control | Tool | When | Gate |
| --- | --- | --- | --- |
| Dependency vulnerabilities (`uv.lock`, `package-lock.json`) | Trivy `fs` | PR, push to `main`, weekly | Fails on fixable HIGH/CRITICAL |
| Committed secrets (working tree) | Trivy `secret`, pre-commit gitleaks | commit, PR | Fails |
| Committed secrets (history) | gitleaks CLI | PR range, full history on `main` and weekly | Fails |
| IaC misconfiguration (Dockerfiles, Kubernetes, Helm, OpenTofu) | Trivy `config`, including the chart rendered with every option on | PR, push to `main`, weekly | Fails on HIGH/CRITICAL |
| Container images (backend, frontend) | Trivy `image` on freshly built images | PR, push to `main`, weekly | Fails on fixable HIGH/CRITICAL |
| New vulnerable or disallowed dependencies in a PR | dependency-review | PR, **public repos only** | Fails on `high` |
| Static analysis | CodeQL (Python, JS/TS, workflows) | PR, push to `main`, weekly, **public repos only** | Code-scanning alerts |
| Dependency and action updates | Dependabot | weekly | PRs |
| SBOM | Trivy CycloneDX per image | release | Attached to release and image |
| Image signatures | cosign keyless | release, public repos (private: opt in with `SIGN_PRIVATE_IMAGES=true`) | Verifiable by digest |
| Build provenance | `attest-build-provenance` | release, **public repos only** | Verifiable attestation |

Policy (severity, unfixed handling, skipped directories) lives in [`trivy.yaml`](../trivy.yaml); gitleaks policy in [`.gitleaks.toml`](../.gitleaks.toml). Run the Trivy checks locally with `make security` (same script and same policy as CI, `scripts/security/trivy-scan.sh`).

## Private repositories and GitHub Advanced Security

Code scanning (SARIF upload), CodeQL, dependency review and artifact attestations require GitHub Advanced Security, which is not available on private repositories of personal accounts. The workflows handle this explicitly:

- Steps that need GHAS are gated on `github.event.repository.visibility == 'public'`. They are *skipped*, not failed, so a private repo is green out of the box and the same files work unchanged once the repository becomes public.
- Results are **always** available without GHAS: JSON and SARIF files are uploaded as workflow artifacts (`trivy-reports`, `gitleaks-report`, retention 30 days), and Trivy writes a Markdown summary to the job summary.
- SARIF is only uploaded for same-repository pushes and PRs; fork PRs receive a read-only token.
- Dependabot alerts and updates work on private repos without GHAS; keep them enabled (Settings → Code security).

## Why Trivy and gitleaks are installed as binaries

Both tools are installed by [`scripts/ci/install-tool.sh`](../scripts/ci/install-tool.sh) from the project's GitHub release, **verified against a SHA-256 that is committed in this repository**. We do not use the `aquasecurity/trivy-action` or a gitleaks action:

- In 2026 the version tags of the official Trivy GitHub Action were re-pointed at malicious commits. Every workflow that referenced a tag (`@v0.x`) ran attacker code with the job's token and secrets, and anything printed to logs was exposed. A mutable tag is not a version.
- A checksum committed to the repo cannot move: if an upstream release is replaced, the build fails with a checksum mismatch instead of executing it.
- The gitleaks CLI is free; the official gitleaks *action* needs a license for organizations.
- Running the CLI directly means the same command works in CI and on a laptop (`make security`).

To upgrade, change `version` and `sha256` in `install-tool.sh` in a normal PR and read the upstream release notes. If you prefer an action, `aquasecurity/setup-trivy` pinned **by commit SHA** that installs a pinned version is the acceptable alternative; never reference the scanning action by tag.

## Handling findings

1. **Fix first.** Upgrade the dependency or base image, or harden the manifest. `make security` reproduces CI.
2. **No fix exists.** `ignore-unfixed: true` already ignores vulnerabilities with no released fix, so they do not block merges. They stay visible in the report.
3. **Accepting a risk** means adding the ID to [`.trivyignore`](../.trivyignore) with all three of:
    - a comment directly above it saying *why* it is not exploitable or not fixable, linking a tracking issue,
    - an expiry date (`CVE-2099-0001 exp:2099-01-31`), at most 90 days out,
    - review by a code owner (the file is covered by CODEOWNERS).

    Expired entries resurface automatically as findings. Never suppress a secret finding: rotate the credential, then remove it from the tree and history.
4. **A leaked secret** is compromised the moment it is pushed. Revoke or rotate it first, then clean the history if needed. Do not rely on deleting the commit.
5. **Gitleaks false positives:** extend the allowlist in `.gitleaks.toml` with a narrow path or regex and a comment. Keep it small; fixtures with fake credentials live under `tests/fixtures/`.

## Supply-chain rules

These apply to every workflow change and are reviewed as security-relevant (CODEOWNERS covers `.github/`).

1. **Pin actions by full commit SHA**, with the human version in a trailing comment: `uses: actions/checkout@<40-hex> # v7.0.1`. Tags and branches are mutable. Dependabot understands the format and bumps SHA and comment together. Resolve SHAs with `gh api repos/<owner>/<repo>/git/ref/tags/<tag>` and dereference annotated tags; never copy a SHA from a blog post.
2. **Pin tool binaries by checksum** (`install-tool.sh`) and container base images by tag (Dependabot bumps them). Never `curl | sh`.
3. **Least privilege.** Top-level `permissions: {}`; each job lists exactly the scopes it needs, with a comment for each write scope. `GITHUB_TOKEN` should default to read-only in repository settings.
4. **Secrets only where needed.** Deployment secrets live in GitHub *Environments* (`staging`, `production`) with required reviewers on production, not in repository-wide secrets. Optional integrations (`ANTHROPIC_API_KEY`, `KUBECONFIG`) make their workflow a no-op when absent.
5. **No credentials left behind.** `actions/checkout` runs with `persist-credentials: false`; the kubeconfig is written with `umask 077` and deleted at the end of the job.
6. **Untrusted input never reaches a shell.** PR titles, bodies, branch names and comments are attacker-controlled. Pass them via `env:` or a file (`$GITHUB_EVENT_PATH`), never `${{ github.event.pull_request.title }}` inside `run:`. CodeQL's `actions` language and actionlint catch the common mistakes.
7. **Timeouts everywhere** (`timeout-minutes`) so a hung or hijacked job cannot burn minutes indefinitely.
8. **Release integrity.** Releases only build from tags on `main` whose `ci-success` is green. Images are addressed by digest, carry a CycloneDX SBOM and, on public repos (or private ones that opt in), are signed with keyless cosign (no long-lived signing key to steal) with SLSA provenance on public repos. Deploys resolve tags to digests and deploy those.
9. **Enable repository protections:** branch ruleset on `main` (required `ci-success`, code-owner review, no force-push), tag protection for `v*`, Dependabot alerts and security updates, secret scanning and push protection where available (free on public repos), and *Require approval for all outside collaborators* for fork PR workflows.

### `pull_request_target` rules

`pull_request_target` runs the workflow from the **base** branch with a **write token and access to secrets**, even when the PR comes from a fork. That makes it the most dangerous trigger in GitHub Actions. We use it only in `pr-labeler.yml` and `automerge.yml`, which need to write labels or enable auto-merge on fork PRs. The rules:

- Never check out the PR head (`ref: ${{ github.event.pull_request.head.* }}`), and never run code from the PR: no `npm install`, `make`, `pip install`, test runners, or scripts from the PR tree. The labeler's single checkout has no `ref`, so it gets the base branch.
- Treat title, body, branch name and labels as data: only via `env:`, parsed by our own base-branch script.
- Keep permissions minimal and the job short; give it no secrets other than `GITHUB_TOKEN`.
- If a workflow needs both PR code and a write token, split it: run the PR code in a `pull_request` workflow (read-only) that uploads an artifact, and let a separate `workflow_run` workflow consume the artifact as untrusted data.

`agent-review.yml` follows the same spirit: the prompt is fixed in the workflow, the model is limited to read-only tools, and fork PRs are skipped for the label trigger because secrets are not available to them.

## Verifying a release

```bash
# Signature (keyless): proves the image was built by this repository's release workflow.
cosign verify \
  --certificate-identity-regexp '^https://github\.com/<owner>/<repo>/\.github/workflows/release\.yml@refs/tags/v' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/<owner>/<repo>/backend@sha256:<digest>

# SBOM attestation
cosign verify-attestation --type cyclonedx \
  --certificate-identity-regexp '^https://github\.com/<owner>/<repo>/\.github/workflows/release\.yml@refs/tags/v' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/<owner>/<repo>/backend@sha256:<digest>

# Build provenance (public repositories)
gh attestation verify oci://ghcr.io/<owner>/<repo>/backend@sha256:<digest> --repo <owner>/<repo>
```

Keyless signatures are written to the public Sigstore transparency log, which includes the repository name. `release.yml` therefore signs automatically only when the repository is public; a private repository opts in by setting the repository variable `SIGN_PRIVATE_IMAGES=true` (accepting that disclosure) or switches to a private Sigstore deployment.
