# ADR-0001: Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-11-01
- **Deciders:** maintainers
- **Related:** [ADR template](0000-template.md), [plans](../plans/README.md)

## Context

Decisions made in chat threads, PR comments, or someone's head are lost. New contributors repeat old debates, and coding agents,
which start every session without memory, cannot tell a deliberate constraint from an accident. We want a cheap, durable,
reviewable place to record the reasoning behind decisions that are hard to reverse.

## Decision

We will record significant architecture decisions as short Markdown files in `docs/adr/`, numbered sequentially
(`NNNN-short-title.md`), created from [`0000-template.md`](0000-template.md), reviewed through normal PRs, and immutable once
accepted. Changing a decision means adding a new ADR that supersedes the old one. Exploratory design work happens in
[`docs/plans/`](../plans/README.md) first.

## Options considered

### Option A: ADRs in the repository (chosen)

Versioned with the code, reviewed in PRs, greppable by humans and agents, no extra tooling. Requires discipline to write them.

### Option B: A wiki or external design-doc tool

Easy to write, but drifts from the code, lacks review and history tied to commits, and is invisible to agents working in the checkout.

### Option C: No formal records

Zero overhead today, but knowledge decays and the same decisions get relitigated.

## Consequences

- Reviewers can ask "is there an ADR for this?" and point to a canonical answer.
- Agent instructions (`AGENTS.md`) tell agents to read `docs/adr/` before changing architecture and to propose an ADR rather than silently deviating.
- Small overhead per significant decision; the template and the "when to write one" guidance keep it light.
- If ADRs pile up unread, prune the index and fold superseded records into a status line rather than deleting history.
