# Security Policy

## Supported versions

Security fixes are provided for the latest released minor version and for the `main` branch. Older versions are not patched;
upgrade to a supported release.

| Version | Supported |
| --- | --- |
| `main` | Yes |
| Latest release | Yes |
| Older releases | No |

## Reporting a vulnerability

**Do not open a public issue, discussion, or pull request for a security problem.**

Report privately through GitHub Security Advisories:

1. Go to the repository's **Security** tab.
2. Choose **Report a vulnerability** (private vulnerability reporting).
3. Describe the issue, affected component and version or commit, reproduction steps or proof of concept, and the impact you expect.

If you cannot use GitHub's private reporting, contact a maintainer listed in [`.github/CODEOWNERS`](.github/CODEOWNERS)
through their GitHub profile and ask for a private channel; do not include details in the first message.

## What to expect

| Step | Target |
| --- | --- |
| Acknowledgement of your report | within 3 business days |
| Initial assessment (valid, severity, affected versions) | within 7 days |
| Fix or mitigation for critical and high severity | within 30 days |
| Fix or mitigation for medium and low severity | within 90 days |
| Public disclosure | after a fix is released, coordinated with you |

These are best-effort targets for a volunteer-run project. We will keep you informed, credit you in the advisory if you wish,
and ask that you give us reasonable time to fix the issue before disclosing it.

## Scope

In scope:

- Application code in `backend/` and `frontend/`, container images, and the Helm chart in `deploy/`.
- Infrastructure code in `infra/` and the CI workflows in `.github/` (for example, injection via untrusted input,
  over-broad permissions, or secrets exposure).
- Dependencies, when the vulnerable code path is reachable from this project.

Out of scope:

- Findings that require a compromised host, a malicious maintainer, or physical access.
- Denial of service through unrealistic volumes of traffic against a self-hosted instance.
- Missing hardening that has no demonstrated impact, and vulnerabilities in dependencies that are not reachable.
- Social engineering of contributors.

## How we keep the project secure

The automated controls (secret scanning, dependency and image scanning, IaC scanning, pinned actions, least-privilege workflow
tokens) are documented in [`docs/security.md`](docs/security.md). Deployment hardening (non-root, read-only filesystems,
external database credentials in Secrets) is described in [`docs/deployment.md`](docs/deployment.md).

## For contributors

Never commit secrets, tokens, or real credentials, not even in tests; use fake values in `.env.example` and test fixtures
(they are allowlisted in `.gitleaks.toml`). If you accidentally commit a secret, treat it as compromised: revoke it first, then
tell a maintainer so history can be cleaned if needed.
