# Sample approaches

Concrete loops you can run today, with prompts. Each one names the skills it uses, its stop conditions, and the
autonomy level it needs ([`self-managed-prs.md`](self-managed-prs.md)). Prompts are starting points: keep them short, refer
to skills and `AGENTS.md` instead of repeating rules, and always include a stop condition.

Conventions used below: `<n>` is an issue or PR number; commands run from the repo root.

## Issue to PR

**Level:** L1 (draft PR) to L2 (marks ready). **Skills:** `writing-issues`, `planning`, `integration-tests` or `playwright-tests`,
`code-review`, `pull-request`, `ci-triage`.

```text
Take issue #<n>. Follow AGENTS.md.
1. Read the issue and the files it names. If it is not agent-ready (testable acceptance criteria, small scope, no
   sensitive paths) or needs a plan, comment what is missing, label status: needs-human, and stop.
2. Claim it: comment the branch name, swap label agent: ready for agent: in-progress.
3. Branch <type>/<n>-<slug> from origin/main. Write the failing test first at the cheapest level that can fail correctly.
4. Implement in small commits. Run make check, then the verification-ladder rungs the change needs.
5. Self-review with the code-review skill; fix blockers and majors.
6. Open a draft PR per the pull-request skill (agent: authored, Verification table with real output, make pr-check green).
7. Watch CI. On red, use the ci-triage skill. When green, mark ready and add agent: review.
Stop and label status: needs-human on any escalation rule in AGENTS.md. Do not merge.
```

What a good run produces: a PR under ~400 lines, a regression test that fails without the change, a Verification table with
counts, no unrelated diffs, a comment on the issue linking the PR.

## Self-review pass

**Skills:** `code-review`. Use a fresh context (Claude Code: `/review`, which runs the read-only `reviewer` subagent).

```text
You did not write this change. Review `git diff origin/main...HEAD` with the code-review skill. Read each changed file in full,
run make check and any test level the diff needs, and try to break it. Report findings (blocker/major/minor/nit) with
path:line, evidence and a suggested fix, then a verdict. Do not edit files and do not approve.
```

Then the author fixes blockers and majors, re-runs the same checks, and notes in the PR what the review covered.

## Review-fix loop

**Level:** L2. **Skills:** `code-review` (as author), `pull-request` (responding to review), `ci-triage`.

```text
PR #<n> has review comments. Using the pull-request skill's "Responding to review" section:
1. gh pr view <n> --comments; gh api repos/{owner}/{repo}/pulls/<n>/comments. Group findings by theme.
2. For each: fix it in a new commit, or reply with evidence it does not apply. Never suppress a check to satisfy a finding.
3. Run the checks that cover the changed area; push; reply to every thread with the commit sha; do not resolve a human's thread.
4. Update the Verification table; re-request review (label agent: review).
Limit: three rounds. If findings keep coming back, or two reviewers conflict, label status: needs-human and summarise the open question.
```

## CI triage

**Level:** L2. **Skills:** `ci-triage`. Claude Code: `/triage-ci <pr-or-run>`.

```text
CI is red on PR #<n>. Use the ci-triage skill: find the first real error (gh run view --log-failed), reproduce locally with the
same make target, classify (real, pre-existing on main, flaky, infrastructure) with evidence, and fix only real failures in
one small commit. Never retry until green, never weaken or skip a check. If it is flaky or infrastructure, say so with
evidence and label status: needs-human. Report the root cause in a PR comment.
```

Example of the report that comes back:

```markdown
**CI triage:** `backend / integration` failed. Root cause: `test_list_is_newest_first` inserts rows with identical
`created_at` and the query had no tiebreaker; reproduced with `make test-integration` (3 of 20 runs). Fixed in `abc1234`
(`ORDER BY created_at DESC, id DESC`) and added `test_ties_on_created_at_are_ordered_by_id`. `make check` and
`make test-integration` pass 20/20.
```

## Dependency updates

**Level:** L3 (label for merge), L4 only for allowlisted patch bumps. **Skills:** `pull-request`, `ci-triage`, `code-review`.

```text
Dependabot opened PR #<n>. Read the release notes between the versions. Run make check and make test-integration (backend) or
make -C frontend build test-e2e (frontend). If anything breaks, fix call sites in the same PR with the smallest change.
Patch or minor and everything green and no behaviour change in the notes: comment the evidence and add status: ready-to-merge.
Major version, security-sensitive package (auth, crypto, HTTP server), failing checks you cannot fix quickly, or unclear notes:
add status: needs-human with a summary of what changed and the risk.
```

## Plan first

**Skills:** `planning`, `writing-issues`. For anything touching more than one package or PR.

```text
Use the planning skill for issue #<n> ("item due dates"). Read docs/architecture.md, docs/conventions.md and existing ADRs.
Copy docs/plans/TEMPLATE.md, fill it in with two real options, a decision, rollout (expand/contract migration), a test plan
mapped to test levels, and PR slices under 400 lines each. Open a docs-only PR and stop; a human accepts the plan.
After acceptance: create one issue per slice using the writing-issues skill, label the well-specified ones agent: ready.
```

## Audit an external repo and raise its score PR by PR

**Skills:** `repo-audit`, `planning`, `writing-issues`, `pull-request`. **Level:** L1 on the target repo.

The `repo-audit` skill scores any repository against the practices in this template (agent instructions, CI, tests,
security, deployment, docs, review flow) and produces a prioritised list of improvements.

```text
Use the repo-audit skill on /path/to/target-repo (this template is the baseline).
1. Run: python3 .agents/skills/repo-audit/scripts/audit.py /path/to/target-repo --format markdown > /tmp/audit.md
2. Read the report; verify the top findings by hand (the scanner is heuristic). Drop anything that does not fit that repo's stack.
3. Turn the gaps into a plan (planning skill): order by value over effort, one PR per item, each independently mergeable,
   safest first (AGENTS.md and hooks, then CI gates, then tests, then deployment hardening).
4. For each slice open an issue (writing-issues skill) and implement the first one as a draft PR in the target repo.
   Include the before/after score from re-running the audit in the PR's Verification table.
Stop after the first PR. Never copy this template wholesale: adapt each practice to the target's languages, CI and conventions.
```

Good outcome: a score trend per PR (for example 41, then 48 after adding `AGENTS.md` and a PR template, then 57 after required
CI checks), each change small enough to review in minutes.

## Triage and issue grooming

**Skills:** `writing-issues`.

```text
List open issues labelled status: needs-triage. For each: reproduce bugs (or ask exactly one concrete question and label
status: blocked), add type: and area: labels, rewrite the description with testable acceptance criteria, and propose agent: ready
only if every item in the skill's agent-ready bar holds. Do not close issues; comment a recommendation instead.
```

## Writing the prompt: a checklist

- [ ] One goal, one deliverable (a PR, a report, a plan), stated first
- [ ] Names the skills and files to start from; says "follow AGENTS.md" rather than restating rules
- [ ] States the verification expected (which make targets, which test level)
- [ ] States what is out of scope
- [ ] Gives the stop conditions and the label to apply when stopping (`status: needs-human`)
- [ ] Bounds loops (maximum rounds) and says explicitly "do not merge" unless the level allows it
