# Documentation

Start here. Everything below is Markdown in the repository, so it is versioned, reviewed, and readable by agents.
The top-level [`README.md`](../README.md) covers what the project is and how to run it; these pages go deeper.

## Contributing and process

| Doc | Read it when |
| --- | --- |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | You are about to make your first change: setup, branches, commits, PRs, labels, review SLAs, definition of done |
| [`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) | You want to know how we treat each other |
| [`../SECURITY.md`](../SECURITY.md) | You found a vulnerability (report privately) |
| [`conventions.md`](conventions.md) | You need the rules: tooling, naming, errors, logging, config, API versioning, migrations, reviewer heuristics |
| [`testing.md`](testing.md) | You are deciding what kind of test to write, or how to run one |
| [`ci.md`](ci.md) | CI is red, or you are changing workflows, labels, or branch protection |

## Design and decisions

| Doc | Read it when |
| --- | --- |
| [`architecture.md`](architecture.md) | You want the system context, containers, and Kubernetes deployment view |
| [`adr/`](adr/README.md) | You want to know *why* something is the way it is, or you are making a hard-to-reverse decision |
| [`plans/`](plans/README.md) | You are starting a non-trivial change and want to design it before coding |

## Operations and security

| Doc | Read it when |
| --- | --- |
| [`deployment.md`](deployment.md) | You are deploying with Docker Compose, Helm, or kind, or provisioning infrastructure |
| [`security.md`](security.md) | You want the scanning, supply-chain, and hardening controls and how to run them |

## Working with coding agents

| Doc | Read it when |
| --- | --- |
| [`../AGENTS.md`](../AGENTS.md) | You are an agent (or configuring one): the tool-agnostic entry point |
| [`agents/README.md`](agents/README.md) | You want the overview: instruction files, skills, hooks, and the issue-to-merge flow |
| [`agents/hooks.md`](agents/hooks.md) | You want to know what each agent hook enforces, how to extend it, or how it can be bypassed |
| [`agents/review.md`](agents/review.md) | You want the layered review flow: self-review, AI reviewer, then code owners |
| [`agents/self-managed-prs.md`](agents/self-managed-prs.md) | You want the autonomy levels, the label state machine, and the guardrails for agent-managed PRs |
| [`agents/sample-approaches.md`](agents/sample-approaches.md) | You want concrete agent loops and prompts to copy |
| [`../.agents/skills/README.md`](../.agents/skills/README.md) | You want the catalogue of repo skills |

## Conventions for these docs

- Docs change in the same PR as the behaviour they describe; stale docs are bugs.
- Link, do not copy: each fact has one home (commands live in the `Makefile`, config in files, decisions in ADRs).
- Keep it short and concrete; prefer a command or a table to a paragraph.
- Markdown is linted by markdownlint (`.markdownlint.yaml`) through pre-commit; fenced code blocks must declare a language.
