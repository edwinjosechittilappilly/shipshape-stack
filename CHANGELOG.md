# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Release notes on GitHub are generated from PR labels
(see `.github/release.yml`); this file records the human-curated highlights.

## [Unreleased]

### Added

- Full-stack starter: FastAPI + Postgres backend, Vite + React frontend, Docker Compose, Helm chart, kind e2e, OpenTofu platform module.
- CI with a single `ci-success` gate, path filters, unit/integration/Playwright/full-stack/kind jobs.
- Security scanning with Trivy (filesystem, IaC, images), gitleaks, CodeQL, SBOM and image signing on release.
- PR hygiene: conventional titles, description checks, automatic type/area/size labels.
- Agent tooling: `AGENTS.md`, reusable skills, safety/format/stop hooks for Claude Code, Codex and Cursor, review and self-managed PR playbooks.
- ShipShape branding: SEO-focused README with badges, FAQ and comparison table, plus a banner / social-preview image.
- repo-audit exits with a clear message on Python older than 3.11 instead of a traceback.
