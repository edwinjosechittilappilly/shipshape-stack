---
name: ci-triage
description: "Use when a CI check fails on a pull request or on main: find the failing job, reproduce it locally with the same make target, classify real vs flaky vs infrastructure, and choose fix-forward or revert. Never retry until green."
---

# CI triage

CI calls `make` targets only (see `docs/ci.md`), so **every CI failure reproduces locally with the
same target**. Your job is to learn *why* it failed, not to make it green.

## Rules

1. **Reproduce before changing anything.** If you cannot reproduce, you do not yet understand it.
2. **Never retry-until-green.** Re-running a job is allowed exactly once, to gather evidence for a flake
   hypothesis, and you must say so in the PR.
3. **Never weaken the check**: no `continue-on-error`, `skip`, `xfail`, deleted test, loosened lint rule,
   raised timeout, `--no-verify`, or removed step to get green. That moves the failure to production.
4. A failure you did not cause still needs an owner: fix it, or file an issue and label `status: needs-human`.

## Procedure

```bash
gh pr checks                                  # which checks failed (add --watch to follow)
gh run list --branch "$(git branch --show-current)" --limit 5
gh run view <run-id> --log-failed             # only the failing steps' logs
gh run view <run-id> --json jobs --jq '.jobs[] | select(.conclusion=="failure") | .name'
```

1. **Find the first real error**, not the last line: scroll up from the failing step to the earliest
   error; later errors are often cascades. Note the exact command the job ran.
2. **Map job -> make target** and run it locally from a clean state:

   | CI job / step | Reproduce with |
   | --- | --- |
   | hygiene (pre-commit) | `uvx pre-commit run --all-files` (or `--files <paths>`) |
   | backend lint / typecheck / test | `make -C backend lint typecheck test` |
   | backend integration | `make test-integration` |
   | frontend lint / typecheck / unit / build | `make -C frontend lint typecheck test build` |
   | frontend React Doctor | `make -C frontend doctor` |
   | e2e mocked | `make -C frontend playwright-install test-e2e` |
   | e2e fullstack | `make test-e2e-fullstack` (then `make down`) |
   | helm / kind | `make helm-lint`, `make kind-e2e` |
   | security (Trivy) | `make security` |
   | PR title/body | `make pr-check TITLE="..." BODY=file` |
   | agent hooks / ci scripts | `make hooks-test`, `python3 -m unittest discover -s scripts/ci/tests -t .` |

3. **Match the environment** if it passes locally: same tool versions (`.python-version`, `.nvmrc`/`engines`), `CI=true`,
   fresh checkout (`git stash -u` or a `git worktree add /tmp/ci origin/<branch>`), clean DB (`make down && make db-up`), no cached build output.
4. **Classify** with evidence:

   | Class | Signals | Action |
   | --- | --- | --- |
   | **Real failure** | Reproduces locally; related to the diff; deterministic | Fix in a new commit; re-run the make target; push |
   | **Pre-existing on main** | Also fails on `origin/main` (check in a worktree / main's latest run) | Not your diff: file/link an issue; fix separately or `status: needs-human`; say so in the PR |
   | **Flaky** | Passes on re-run/locally, fails intermittently, timing/order/port/network dependent, same test failing on unrelated PRs | Find the shared state or race and fix it (`integration-tests` / `playwright-tests` flake policy). If unfixable now: issue + `status: needs-human` |
   | **Infrastructure** | Runner/network errors, registry 5xx, action download failures, rate limits, outage on githubstatus | One re-run to confirm; note it in the PR; do not change code |
   | **Config drift** | New tool version, expired token, changed base image, deprecated action | Pin or update deliberately in its own `ci:`/`chore:` PR |

5. **Fix small and targeted**: one failure, one commit (`fix(backend): ...` / `test: ...` / `ci: ...`). Add the
   regression test if the failure revealed a gap. Re-run the exact make target, then the wider `make check`.
6. **Report** in the PR: what failed, root cause, evidence, what you changed. Update the Verification table.

## Fix-forward or revert?

| Situation | Choose |
| --- | --- |
| Failure on your open PR | Fix-forward on the branch (never merge red) |
| `main` is red, fix is small, obvious and tested (< ~30 min) | Fix-forward in a PR, `ci-success` required as usual |
| `main` is red, cause unclear, or a fix needs design, or it blocks others | **Revert** the culprit PR (`git revert -m1 <merge>` / squash commit) via PR titled `revert: ...`, then re-land properly |
| Production impact | Revert first, investigate after; label `status: needs-human` and notify the owner |
| Flaky test blocking many PRs | Quarantine only with human approval: skip with a linked issue + owner + deadline |

Agents may open the revert PR but a human merges reverts of `main` unless `docs/agents/self-managed-prs.md` level L3+ applies.

## Escalate (`status: needs-human`) when

- you cannot reproduce after two serious attempts, or it needs credentials/secrets/infrastructure you do not have
- the fix requires changing CI config, required checks, branch protection, or security policy
- the same check fails after two different fixes, or the failure is on `main` and cause is unknown
- you would have to disable or loosen a check to proceed

Leave a comment with: failing job link, the command you ran, what you observed, hypotheses ruled out, and what you need.

## Checklist

- [ ] Located the first real error and the exact CI command
- [ ] Reproduced locally with the same make target (or documented why not)
- [ ] Classified with evidence; not retried blindly
- [ ] Fixed the cause without weakening any check
- [ ] Re-ran the failing target and `make check`; Verification table updated
