"""Checks: documentation, agent readiness, PR & issue hygiene, developer experience."""

from __future__ import annotations

import json
import os
import re

from registry import F, H, P, Result, check, graded
from repo_context import Repo

DOCS, AGENT, HYGIENE, DX = "docs", "agent", "hygiene", "dx"


def lines_of(text: str) -> int:
    return sum(1 for ln in text.splitlines() if ln.strip())


# ======================================================================================================================
# Documentation & onboarding
# ======================================================================================================================
def _readme(r: Repo) -> str | None:
    return next((f for f in r.files if "/" not in f and re.match(r"(?i)^readme(\.(md|rst|txt|adoc))?$", f)), None)


@check(
    "DOC-README", DOCS, "README with substance", 3, "S",
    why="First file humans and agents read. Without it nobody knows what the project is, who it is for, or where to start.",
    detect="README.* at repo root; pass at 25+ non-blank lines, partial for a stub.",
    fix="Write a README: purpose, quickstart, layout, how to test, where docs/contributing live.",
    ref="README.md",
)
def _doc_readme(r: Repo) -> Result:
    p = _readme(r)
    if not p:
        return F("no README at the repository root")
    n = lines_of(r.read(p))
    return P(f"{p}: {n} non-blank lines") if n >= 25 else H(f"{p} is a stub ({n} non-blank lines)")


@check(
    "DOC-README-RUN", DOCS, "README shows how to install, run and test", 3, "S",
    why="A newcomer (or a fresh agent session) must go from clone to running tests using only the README.",
    detect="Fenced code blocks under setup/run/usage headings, plus a test command inside a code block.",
    fix="Add Quickstart (prerequisites, one setup command, run command) and Testing sections with copy-pasteable commands.",
    ref="README.md",
)
def _doc_readme_run(r: Repo) -> Result:
    p = _readme(r)
    if not p:
        return F("no README")
    text = r.read(p)
    blocks = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
    has_run_heading = bool(re.search(r"(?im)^#{1,4}\s.*(install|setup|set up|getting started|quick ?start|usage|run|develop)", text))
    has_test_cmd = any(re.search(r"\b(test|pytest|check|verify|lint)\b", b) for b in blocks)
    if blocks and has_run_heading and has_test_cmd:
        return P(f"{len(blocks)} code blocks, run/setup section and a test command")
    if blocks and (has_run_heading or has_test_cmd):
        return H("code blocks present but " + ("no test command shown" if has_run_heading else "no setup/run section"))
    return F("no runnable commands in the README")


def _find_named(r: Repo, names: set[str], dirs=("", ".github", "docs")) -> str | None:
    for f in r.files:
        d, _, b = f.rpartition("/")
        if d in dirs and b.lower() in names:
            return f
    return None


@check(
    "DOC-LICENSE", DOCS, "License file", 2, "S",
    why="Without a license nobody (human or agent) may legally reuse or contribute to the code.",
    detect="LICENSE / LICENCE / COPYING at repo root.",
    fix="Add a LICENSE file (choose one at choosealicense.com; Apache-2.0 or MIT are common).",
    ref="LICENSE",
)
def _doc_license(r: Repo) -> Result:
    p = _find_named(r, {"license", "license.md", "license.txt", "licence", "licence.md", "copying", "copying.md"}, dirs=("",))
    return P(p) if p else F("no LICENSE file")


@check(
    "DOC-CONTRIB", DOCS, "CONTRIBUTING guide", 2, "S",
    why="Defines the branch/commit/PR/test workflow so contributions and agent-authored PRs arrive in the shape reviewers expect.",
    detect="CONTRIBUTING.md at root, .github/ or docs/; pass at 30+ non-blank lines.",
    fix="Document setup, branching, commit/PR conventions, the verification ladder and review expectations.",
    ref="CONTRIBUTING.md",
)
def _doc_contrib(r: Repo) -> Result:
    p = _find_named(r, {"contributing.md", "contributing.rst", "contributing"})
    if not p:
        return F("no CONTRIBUTING guide")
    n = lines_of(r.read(p))
    return P(f"{p}: {n} lines") if n >= 30 else H(f"{p} is thin ({n} lines)")


@check(
    "DOC-COC", DOCS, "Code of conduct", 1, "S",
    why="Sets behaviour expectations for community projects; required by most open-source platforms' community standards.",
    detect="CODE_OF_CONDUCT.md at root, .github/ or docs/.",
    fix="Adopt the Contributor Covenant and add a reporting contact.",
    ref="CODE_OF_CONDUCT.md",
)
def _doc_coc(r: Repo) -> Result:
    p = _find_named(r, {"code_of_conduct.md", "code-of-conduct.md", "code_of_conduct"})
    return P(p) if p else F("no CODE_OF_CONDUCT.md")


@check(
    "DOC-CHANGELOG", DOCS, "Changelog or release notes source", 1, "S",
    why="Lets users and agents see what changed between versions without reading every PR.",
    detect="CHANGELOG/HISTORY/NEWS at root or docs/; partial when only an automated tool (changesets, release-please) is configured.",
    fix="Keep a CHANGELOG.md (Keep a Changelog format) or configure release notes generation.",
    ref="CHANGELOG.md",
)
def _doc_changelog(r: Repo) -> Result:
    p = _find_named(r, {"changelog.md", "changelog", "changelog.rst", "history.md", "news.md", "changes.md", "releases.md"}, dirs=("", "docs"))
    if p:
        return P(p)
    auto = r.glob(".changeset/config.json", "release-please-config.json", "cliff.toml", ".releaserc*", ".github/release-drafter.yml")
    return H(f"automated release notes configured ({auto[0]}) but no changelog file") if auto else F("no changelog")


@check(
    "DOC-DOCS", DOCS, "docs/ directory", 2, "M",
    why="Longer-lived knowledge (architecture, testing, deployment) does not fit in a README; agents load it on demand instead of guessing.",
    detect="docs/ (or doc/, documentation/, mkdocs.yml) with 3+ Markdown files passes; 1-2 partial.",
    fix="Create docs/ with an index plus architecture, testing and deployment guides.",
    ref=("docs/README.md", "docs/architecture.md", "docs/testing.md"),
)
def _doc_docs(r: Repo) -> Result:
    md = [f for f in r.files if re.match(r"(?i)^(docs?|documentation)/.+\.(md|mdx|rst|adoc)$", f)]
    if len(md) >= 3:
        return P(f"{len(md)} documents under docs/")
    if md or r.glob("mkdocs.yml", "docusaurus.config.*", "book.toml"):
        return H(f"only {len(md)} documents; add architecture/testing/deployment guides")
    return F("no docs/ directory")


@check(
    "DOC-ARCH", DOCS, "Architecture overview", 1, "S",
    why="A one-page map of components, boundaries and data flow stops agents from inventing structure and speeds up human onboarding.",
    detect="ARCHITECTURE.md, docs/architecture*, docs/design*, docs/overview*.",
    fix="Write docs/architecture.md: components, data flow, key decisions, where code lives.",
    ref="docs/architecture.md",
)
def _doc_arch(r: Repo) -> Result:
    hit = r.first("ARCHITECTURE.md", "architecture.md", "docs/architecture*", "docs/design*", "docs/overview*", "doc/architecture*", "docs/**/architecture*.md")
    return P(hit) if hit else F("no architecture document")


@check(
    "DOC-ADR", DOCS, "Architecture decision records", 1, "S",
    why="Records why decisions were made, so they are not silently reversed by the next contributor or agent.",
    detect="docs/adr, docs/decisions, adr/ or doc/adr with Markdown records (2+ passes).",
    fix="Adopt ADRs: add docs/adr/README.md, a template and one record per significant decision.",
    ref=("docs/adr/README.md", "docs/adr/0000-template.md"),
)
def _doc_adr(r: Repo) -> Result:
    md = [f for f in r.files if re.match(r"(?i)^(docs?/)?(adrs?|decisions)/.+\.md$", f)]
    if len(md) >= 2:
        return P(f"{len(md)} ADR files")
    return H("one ADR file; add a template and real records") if md else F("no ADR directory")


@check(
    "DOC-PLANS", DOCS, "Planning documents (plans/RFCs)", 1, "S",
    why="Written plans make work sliceable and reviewable before code exists, and give agents an executable spec.",
    detect="docs/plans, docs/rfcs, rfcs/, docs/design, docs/proposals or docs/specs with Markdown (2+ passes).",
    fix="Add docs/plans/ with a TEMPLATE.md (goal, slices, acceptance, risks) and write plans for non-trivial work.",
    ref=("docs/plans/README.md", "docs/plans/TEMPLATE.md"),
)
def _doc_plans(r: Repo) -> Result:
    md = [f for f in r.files if re.match(r"(?i)^(docs?/)?(plans|rfcs?|proposals|specs|design-docs)/.+\.md$", f)]
    if len(md) >= 2:
        return P(f"{len(md)} planning documents")
    return H("one planning document") if md else F("no plans/RFC directory")


def _pkg_dirs(r: Repo) -> list[str]:
    return sorted({d for _, d in r.manifest_dirs() if d})


@check(
    "DOC-PKG-README", DOCS, "Each package has its own README", 1, "S",
    why="In a monorepo an agent working in one package should not have to infer its commands from the root README.",
    detect="Every non-root manifest directory (package.json, pyproject.toml, go.mod, ...) contains a README.",
    fix="Add a short README per package: purpose, commands (`make -C <pkg> ...`), layout.",
    ref=("backend/README.md", "frontend/README.md"),
    applies=lambda r: r.monorepo and len(_pkg_dirs(r)) >= 1,
    na="single-package repository",
)
def _doc_pkg_readme(r: Repo) -> Result:
    pk = _pkg_dirs(r)
    missing = [d for d in pk if not any(r.has(f"{d}/{n}") for n in ("README.md", "README.rst", "README"))]
    return graded(1 - len(missing) / len(pk), f"{len(pk) - len(missing)}/{len(pk)} packages have a README" + (f"; missing: {', '.join(missing[:5])}" if missing else ""))


# ======================================================================================================================
# Agent readiness
# ======================================================================================================================
INSTR_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md", ".cursorrules", ".windsurfrules", ".clinerules", ".cursor/rules/*")


def _instr(r: Repo) -> list[str]:
    return r.glob(*INSTR_FILES)


@check(
    "AGT-INSTRUCTIONS", AGENT, "Agent instruction file (AGENTS.md)", 4, "S",
    why="The single most effective lever for agent output: build/test commands, conventions and boundaries loaded at session start.",
    detect="AGENTS.md at root passes; only vendor-specific files (CLAUDE.md, copilot-instructions, .cursorrules, GEMINI.md) is partial.",
    fix="Write AGENTS.md (agent-agnostic): commands, repo map, conventions, verification ladder, hard boundaries.",
    ref="AGENTS.md",
)
def _agt_instr(r: Repo) -> Result:
    if r.has("AGENTS.md"):
        n = lines_of(r.read("AGENTS.md"))
        return P(f"AGENTS.md ({n} non-blank lines)") if n >= 15 else H(f"AGENTS.md is a stub ({n} lines)")
    other = _instr(r)
    if other:
        return H(f"only vendor-specific instructions ({other[0]}); add AGENTS.md so every agent reads the same rules")
    return F("no agent instruction file")


@check(
    "AGT-INSTR-QUALITY", AGENT, "Instructions are actionable", 3, "S",
    why="Vague prose does not change agent behaviour; exact commands, boundaries and a definition of done do.",
    detect="Counts six signals in the instruction files: commands, conventions, repo map, hard boundaries, verification steps, PR/commit workflow. 5+ passes, 3+ partial; over 500 lines caps at partial.",
    fix="Add the missing sections; keep the file short and link to docs/ for depth.",
    ref="AGENTS.md",
    applies=lambda r: bool(_instr(r)),
    na="no instruction file to assess",
)
def _agt_quality(r: Repo) -> Result:
    files = _instr(r)
    text = "\n".join(r.read(f) for f in files)
    sig = {
        "commands": bool(re.search(r"`[^`\n]*\b(make|npm|pnpm|yarn|pytest|uv|cargo|go|mvn|gradle|just|poetry|pip|bundle|dotnet|composer)\b[^`\n]*`", text)),
        "conventions": bool(re.search(r"(?i)\b(convention|code style|naming|formatting|lint)", text)),
        "repo map": bool(re.search(r"(?i)\b(structure|layout|directory|repo map|architecture|where to find|monorepo)", text)),
        "boundaries": bool(re.search(r"(?i)\b(never|do not|don't|must not|avoid|ask first|forbidden|off.limits)\b", text)),
        "verification": bool(re.search(r"(?i)\b(verif|definition of done|before (you )?(commit|push|open|finish)|make check|run (the )?tests)", text)),
        "workflow": bool(re.search(r"(?i)\b(pull request|\bPRs?\b|commit message|conventional commit|branch)", text)),
    }
    n = sum(sig.values())
    missing = [k for k, v in sig.items() if not v]
    longest = max(lines_of(r.read(f)) for f in files)
    note = f"{n}/6 signals" + (f"; missing: {', '.join(missing)}" if missing else "")
    if longest > 500:
        return H(f"{note}; longest file has {longest} lines, agents skim past ~500; move depth into docs/")
    return P(note) if n >= 5 else H(note) if n >= 3 else F(note)


def _claude_bridge_applies(r: Repo) -> bool:
    return r.has("AGENTS.md")


@check(
    "AGT-CLAUDE-BRIDGE", AGENT, "CLAUDE.md points at AGENTS.md", 1, "S",
    why="Claude Code reads CLAUDE.md, not AGENTS.md; without a bridge it silently ignores your agent rules.",
    detect="CLAUDE.md exists and is a symlink to, or references (`@AGENTS.md`), AGENTS.md. Only applies when AGENTS.md exists.",
    fix="Create CLAUDE.md containing `@AGENTS.md` plus any Claude-specific notes (or symlink it).",
    ref="CLAUDE.md",
    applies=_claude_bridge_applies,
    na="no AGENTS.md",
)
def _agt_bridge(r: Repo) -> Result:
    if not r.has("CLAUDE.md"):
        return F("AGENTS.md exists but CLAUDE.md does not, so Claude Code will not load it")
    if r.is_symlink("CLAUDE.md") or re.search(r"AGENTS\.md", r.read("CLAUDE.md")):
        return P("CLAUDE.md links to AGENTS.md")
    return H("CLAUDE.md exists but does not reference AGENTS.md; rules will drift apart")


def _skill_dirs(r: Repo) -> list[str]:
    seen: dict[str, str] = {}
    for base in (".agents/skills", ".claude/skills", ".codex/skills", ".cursor/skills", ".github/skills", "skills"):
        for name in r.listdir(base):
            md = os.path.join(r.root, base, name, "SKILL.md")
            if os.path.isfile(md):
                seen.setdefault(os.path.realpath(md), f"{base}/{name}")
    return sorted(seen.values())


@check(
    "AGT-SKILLS", AGENT, "Reusable agent skills", 3, "M",
    why="Skills package repeatable procedures (open a PR, write tests, triage CI) so agents follow your process instead of improvising.",
    detect="Directories with SKILL.md under .agents/skills, .claude/skills, .codex/skills, .cursor/skills. 3+ passes, 1-2 partial.",
    fix="Add skills for your recurring workflows: pull-request, code-review, planning, ci-triage, tests.",
    ref=(".agents/skills/pull-request/SKILL.md", ".agents/skills/code-review/SKILL.md", ".agents/skills/ci-triage/SKILL.md"),
)
def _agt_skills(r: Repo) -> Result:
    s = _skill_dirs(r)
    if len(s) >= 3:
        return P(f"{len(s)} skills: {', '.join(os.path.basename(x) for x in s[:6])}")
    return H(f"{len(s)} skill(s); aim for the workflows you repeat") if s else F("no skills directory with SKILL.md files")


@check(
    "AGT-SKILLS-VALID", AGENT, "Skill files are well-formed", 1, "S",
    why="A skill is only discovered if its frontmatter has a name and a description that says when to use it.",
    detect="Each SKILL.md starts with YAML frontmatter holding `name` (matching its directory) and a description of 40+ characters.",
    fix="Fix frontmatter: `name: <dir-name>` and `description:` starting with 'Use when ...'.",
    ref=".agents/skills/pull-request/SKILL.md",
    applies=lambda r: bool(_skill_dirs(r)),
    na="no skills",
)
def _agt_skills_valid(r: Repo) -> Result:
    dirs, bad = _skill_dirs(r), []
    for d in dirs:
        text = r.read(f"{d}/SKILL.md")
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
        if not m:
            bad.append(f"{d} (no frontmatter)")
            continue
        name = re.search(r"(?m)^name:\s*['\"]?([^\n'\"]+)", m.group(1))
        desc = re.search(r"(?m)^description:\s*(.*)", m.group(1))
        if not name or name.group(1).strip() != os.path.basename(d):
            bad.append(f"{d} (name != directory)")
        elif not desc or (len(desc.group(1).strip(" >|\"'")) < 40 and not re.match(r"^[>|]", desc.group(1).strip())):
            bad.append(f"{d} (description too short)")
    return graded(1 - len(bad) / len(dirs), f"{len(dirs) - len(bad)}/{len(dirs)} valid" + (f"; problems: {'; '.join(bad[:4])}" if bad else ""))


HOOK_FILES = (".claude/settings.json", ".claude/settings.local.json", ".codex/hooks.json", ".cursor/hooks.json", ".github/hooks/*.json", ".gemini/settings.json")
HOOK_EVENTS = re.compile(r'"(PreToolUse|PostToolUse|Stop|SessionStart|UserPromptSubmit|PermissionRequest|beforeShellExecution|afterFileEdit|beforeSubmitPrompt|preToolUse|postToolUse|stop|beforeReadFile)"')


@check(
    "AGT-HOOKS", AGENT, "Agent hooks (guard, format, stop gate)", 2, "M",
    why="Hooks enforce rules deterministically (block destructive commands, format edits, gate 'done' on checks) where prose instructions are only advisory.",
    detect="Hook configs for Claude/Codex/Cursor/Gemini: 2+ configs or 2+ distinct events pass; one event is partial.",
    fix="Add hooks that block destructive shell commands, auto-format edited files and run a fast check before the agent stops.",
    ref=(".claude/settings.json", ".codex/hooks.json", ".cursor/hooks.json", "scripts/agent-hooks/"),
)
def _agt_hooks(r: Repo) -> Result:
    cfgs, events = [], set()
    for f in r.glob(*HOOK_FILES):
        t = r.read(f)
        if '"hooks"' in t or f.endswith("hooks.json"):
            cfgs.append(f)
            events |= set(HOOK_EVENTS.findall(t))
    if len(cfgs) >= 2 or len(events) >= 2:
        return P(f"{len(cfgs)} hook config(s), events: {', '.join(sorted(events))}")
    return H(f"{cfgs[0]} defines {len(events)} event") if cfgs else F("no agent hook configuration")


@check(
    "AGT-PERMISSIONS", AGENT, "Agent permission allow/deny lists", 2, "S",
    why="Pre-approved safe commands remove prompt fatigue; a deny-list keeps secrets (.env, keys) out of the model's context.",
    detect=".claude/settings.json with `permissions`; pass when `deny` covers .env files, partial without it.",
    fix="Add allow rules for make/test/read-only git+gh and deny rules for .env, *.pem, secrets/ and ssh keys.",
    ref=".claude/settings.json",
)
def _agt_perms(r: Repo) -> Result:
    for f in r.glob(".claude/settings.json", ".claude/settings.local.json"):
        try:
            data = json.loads(r.read(f))
        except ValueError:
            continue
        perms = data.get("permissions") if isinstance(data, dict) else None
        if isinstance(perms, dict):
            deny = " ".join(perms.get("deny", []))
            return P(f"{f}: {len(perms.get('allow', []))} allow, {len(perms.get('deny', []))} deny rules incl. .env") if ".env" in deny else H(f"{f} has permissions but the deny-list does not cover .env files")
    return F("no agent permission configuration")


@check(
    "AGT-ISSUE-TEMPLATE", AGENT, "Agent-ready issue template", 2, "S",
    why="Agents execute well-specified tickets; a template forcing acceptance criteria, scope limits and verification turns issues into runnable tasks.",
    detect="Issue template containing acceptance criteria plus verification/out-of-scope/agent fields passes; acceptance criteria alone is partial.",
    fix="Add an issue form (e.g. 'task') with Goal, Acceptance criteria, Out of scope, How to verify and an agent-ready checkbox.",
    ref=".github/ISSUE_TEMPLATE/task.yml",
)
def _agt_issue(r: Repo) -> Result:
    tpls = r.glob(".github/ISSUE_TEMPLATE/*.yml", ".github/ISSUE_TEMPLATE/*.yaml", ".github/ISSUE_TEMPLATE/*.md", ".github/issue_template.md", ".github/ISSUE_TEMPLATE.md")
    best = "none"
    for t in tpls:
        low = r.read(t).lower()
        if "acceptance" in low:
            if re.search(r"agent|verif|out of scope|definition of done", low):
                return P(f"{t} has acceptance criteria and verification/agent fields")
            best = t
    return H(f"{best} has acceptance criteria but no verification/out-of-scope/agent fields") if best != "none" else F("no issue template with acceptance criteria")


@check(
    "AGT-REVIEW", AGENT, "Automated/agent code review configured", 2, "M",
    why="A second reviewer that follows your rules catches issues before a human looks; a review skill lets authors self-review the same way.",
    detect="Review-bot config (.coderabbit.yaml, greptile, bugbot, claude/copilot/codex review workflow) and a review skill. Both passes; either is partial.",
    fix="Add .coderabbit.yaml (or equivalent) with path instructions and a code-review skill that mirrors your review rubric.",
    ref=(".coderabbit.yaml", ".agents/skills/code-review/SKILL.md", ".github/workflows/agent-review.yml"),
)
def _agt_review(r: Repo) -> Result:
    tool = r.glob(".coderabbit.y*ml", ".greptile*", "greptile.json", ".cursor/BUGBOT.md", ".sourcery.y*ml", ".pr_agent.toml", ".gemini/styleguide.md")
    wf = [w.path for w in r.workflows() if re.search(r"(?i)claude-code-action|copilot|coderabbit|codex|agent-review|gemini-cli|pr-agent|qodo", w.code + w.path)]
    skill = [s for s in _skill_dirs(r) if re.search(r"review", os.path.basename(s))]
    has_tool = bool(tool or wf)
    ev = f"review bot: {(tool + wf)[0] if has_tool else 'none'}; review skill: {skill[0] if skill else 'none'}"
    return P(ev) if has_tool and skill else H(ev) if has_tool or skill else F("no automated review tooling and no review skill")


@check(
    "AGT-DOCS", AGENT, "Agent workflow documentation", 1, "S",
    why="Explains how agents are expected to branch, verify, open PRs and hand off, so humans can supervise and improve the loop.",
    detect="docs/agents/, docs/agent*.md, docs/ai*.md or a dedicated agent-workflow section file.",
    fix="Document the agent workflow: roles, labels, review flow, escalation (`status: needs-human`), what agents may never do.",
    ref="docs/agents/",
)
def _agt_docs(r: Repo) -> Result:
    hit = r.first("docs/agents/*.md", "docs/agents.md", "docs/agent*.md", "docs/ai*.md", "docs/**/agent-workflow*.md", "docs/**/ai-*.md")
    return P(hit) if hit else F("no agent workflow documentation under docs/")


@check(
    "AGT-COMMANDS", AGENT, "Custom agent commands", 1, "S",
    why="Slash commands/prompts turn the team's best prompts (plan, review, verify) into one keystroke.",
    detect="Files under .claude/commands, .cursor/commands, .codex/prompts or .agents/commands.",
    fix="Add commands for plan, review and verify that invoke the matching skills.",
    ref=".claude/commands/",
)
def _agt_commands(r: Repo) -> Result:
    hit = r.first(".claude/commands/*.md", ".cursor/commands/*", ".codex/prompts/*", ".agents/commands/*")
    return P(hit) if hit else F("no custom agent commands")


def _labels_file(r: Repo) -> str | None:
    return r.first(".github/labels.y*ml", ".github/labels.json", ".github/labels.toml")


@check(
    "AGT-LABELS", AGENT, "Agent labels exist", 1, "S",
    why="Labels such as `agent: ready` and `status: needs-human` are the hand-off protocol between humans and agents.",
    detect="Labels-as-code file defines labels with 'agent' in their name. Only applies when a labels file exists.",
    fix="Add `agent: ready`, `agent: in-progress`, `agent: authored`, `agent: review`, `status: needs-human` to labels.yml.",
    ref=".github/labels.yml",
    applies=lambda r: _labels_file(r) is not None,
    na="no labels-as-code file",
)
def _agt_labels(r: Repo) -> Result:
    f = _labels_file(r)
    n = len(re.findall(r"(?i)agent\s*[:/-]", r.read(f)))
    return P(f"{n} agent labels in {f}") if n >= 2 else H(f"{n} agent label in {f}") if n else F(f"{f} defines no agent labels")


# ======================================================================================================================
# PR & issue hygiene
# ======================================================================================================================
def _pr_template(r: Repo) -> str | None:
    return r.first(".github/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE.md", "pull_request_template.md", "PULL_REQUEST_TEMPLATE.md", "docs/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE/*.md")


@check(
    "HYG-PR-TEMPLATE", HYGIENE, "PR template with required sections", 3, "S",
    why="Forces every PR (including agent-authored ones) to state intent, changes and how it was verified; reviewers stop asking the same questions.",
    detect="pull_request_template.md with 3+ headings including a summary and verification/testing section.",
    fix="Add .github/pull_request_template.md: Summary, Linked issue, Changes, Verification, Risk and rollback, Checklist.",
    ref=".github/pull_request_template.md",
)
def _hyg_pr(r: Repo) -> Result:
    p = _pr_template(r)
    if not p:
        return F("no pull request template")
    t = r.read(p)
    heads = re.findall(r"(?m)^#{1,4}\s+(.+)$", t)
    ok = len(heads) >= 3 and re.search(r"(?i)summary|description|what", " ".join(heads)) and re.search(r"(?i)verif|test", " ".join(heads))
    return P(f"{p}: {len(heads)} sections") if ok else H(f"{p} exists but lacks summary and/or verification sections")


@check(
    "HYG-PR-CHECK", HYGIENE, "PR title/description validated in CI", 2, "M",
    why="Machine-checked conventions (Conventional Commit titles, required headings) make labels, changelogs and release notes automatable.",
    detect="CI references semantic-pull-request, commitlint, a check_pr script, danger or similar; a commitlint config alone is partial.",
    fix="Add a pr-checks workflow that validates the title and required headings (adapt scripts/ci/check_pr.py).",
    ref=(".github/workflows/pr-checks.yml", "scripts/ci/check_pr.py"),
)
def _hyg_prcheck(r: Repo) -> Result:
    rx = r"semantic-pull-request|commitlint|pr[-_ ]?title|check[_-]pr|pr[-_]check|conventional[-_ ]?commits?|danger(js)?|pull[-_]request[-_]lint|gitlint|validate[-_ ]pr"
    if re.search(rx, r.ci_text(), re.I):
        return P("PR validation step found in CI")
    cfg = r.first("commitlint.config.*", ".commitlintrc*")
    return H(f"{cfg} exists but CI does not validate PR titles") if cfg else F("no PR title/description validation")


@check(
    "HYG-ISSUE-FORMS", HYGIENE, "Issue forms", 3, "S",
    why="Structured forms produce complete bug reports and tasks; free-text issues cost a round of clarification each.",
    detect=".github/ISSUE_TEMPLATE/*.yml forms with `body:` (2+ passes); Markdown-only templates or one form is partial.",
    fix="Add bug_report.yml, feature_request.yml and task.yml issue forms with required fields.",
    ref=".github/ISSUE_TEMPLATE/bug_report.yml",
)
def _hyg_forms(r: Repo) -> Result:
    forms = [f for f in r.glob(".github/ISSUE_TEMPLATE/*.yml", ".github/ISSUE_TEMPLATE/*.yaml") if not f.endswith("config.yml") and "body:" in r.read(f)]
    if len(forms) >= 2:
        return P(f"{len(forms)} issue forms")
    if forms or r.glob(".github/ISSUE_TEMPLATE/*.md", ".github/ISSUE_TEMPLATE.md"):
        return H("only one form or Markdown templates; use 2+ YAML forms with required fields")
    return F("no issue templates")


@check(
    "HYG-ISSUE-CONFIG", HYGIENE, "Issue chooser configured", 1, "S",
    why="Routes questions and security reports away from the issue tracker and blocks empty issues.",
    detect=".github/ISSUE_TEMPLATE/config.yml with blank_issues_enabled and/or contact_links.",
    fix="Add config.yml: `blank_issues_enabled: false` and contact links (discussions, security policy).",
    ref=".github/ISSUE_TEMPLATE/config.yml",
)
def _hyg_issue_cfg(r: Repo) -> Result:
    f = r.first(".github/ISSUE_TEMPLATE/config.y*ml")
    return P(f) if f and re.search(r"blank_issues_enabled|contact_links", r.read(f)) else F("no issue chooser config")


@check(
    "HYG-LABELS-CODE", HYGIENE, "Labels defined as code", 2, "S",
    why="A versioned label taxonomy (type, area, size, status, agent) makes triage, automation and agent hand-offs reproducible.",
    detect=".github/labels.yml|json|toml; pass at 10+ labels, partial below.",
    fix="Add .github/labels.yml and a sync workflow (labels-sync.yml).",
    ref=(".github/labels.yml", ".github/workflows/labels-sync.yml"),
)
def _hyg_labels(r: Repo) -> Result:
    f = _labels_file(r)
    if not f:
        return F("no labels-as-code file")
    n = len(re.findall(r'(?m)^\s*-?\s*"?name"?\s*:', r.read(f)))
    return P(f"{f}: {n} labels") if n >= 10 else H(f"{f}: only {n} labels")


@check(
    "HYG-LABELER", HYGIENE, "Automatic PR labeling", 2, "M",
    why="Auto-applied type/area/size labels let reviewers and automation filter work without manual bookkeeping.",
    detect=".github/labeler.yml plus a workflow using actions/labeler or a labeling script; either alone is partial.",
    fix="Add labeler.yml path rules and a pr-labeler workflow (type from title, size from diff).",
    ref=(".github/labeler.yml", ".github/workflows/pr-labeler.yml", "scripts/ci/pr_labels.py"),
)
def _hyg_labeler(r: Repo) -> Result:
    cfg = r.first(".github/labeler.y*ml")
    wf = bool(re.search(r"actions/labeler|pr_labels|addLabels|add-label|labeler", "\n".join(w.code for w in r.workflows())))
    if cfg and wf:
        return P("labeler config and workflow")
    return H("labeler config without a workflow" if cfg else "labeling workflow without path rules") if cfg or wf else F("no automatic PR labeling")


@check(
    "HYG-RELEASE-NOTES", HYGIENE, "Release notes categories configured", 1, "S",
    why="Categorised release notes are generated for free when PRs carry type labels.",
    detect=".github/release.yml, release-drafter, release-please, changesets, git-cliff or semantic-release config.",
    fix="Add .github/release.yml mapping labels to changelog categories.",
    ref=".github/release.yml",
)
def _hyg_notes(r: Repo) -> Result:
    f = r.first(".github/release.y*ml", ".github/release-drafter.y*ml", "release-please-config.json", ".changeset/config.json", "cliff.toml", ".releaserc*", "release.config.*")
    return P(f) if f else F("no release notes configuration")


# ======================================================================================================================
# Developer experience
# ======================================================================================================================
GROUPS = {
    "setup": {"setup", "install", "bootstrap", "init", "deps", "dev-setup", "prepare"},
    "lint": {"lint", "check", "vet", "lint-check", "quality", "verify", "validate"},
    "format": {"format", "fmt", "style", "prettier", "lint-fix", "fix", "format-fix"},
    "test": {"test", "tests", "check", "ci", "pytest", "unit"},
    "run": {"run", "dev", "start", "serve", "up", "build"},
}


def _task_names(r: Repo) -> set[str]:
    names: set[str] = set()
    for f in ("Makefile", "makefile", "GNUmakefile"):
        if r.has(f):
            names |= {m for m in re.findall(r"(?m)^([A-Za-z0-9][A-Za-z0-9_.-]*)\s*:(?!=)", r.read(f))}
    for f in ("justfile", "Justfile"):
        if r.has(f):
            names |= set(re.findall(r"(?m)^([a-z][a-z0-9_-]*)[^\n:=]*:(?!=)", r.read(f)))
    for f in ("Taskfile.yml", "Taskfile.yaml"):
        if r.has(f):
            names |= set(re.findall(r"(?m)^  ([A-Za-z0-9:_-]+):\s*$", r.read(f)))
    if r.has("package.json"):
        try:
            names |= set(json.loads(r.read("package.json")).get("scripts", {}))
        except (ValueError, AttributeError):
            pass
    if r.has("noxfile.py") or r.has("tox.ini"):
        names |= {"test", "lint"}
    for f in ("mise.toml", ".mise.toml"):
        if r.has(f):
            names |= set(re.findall(r"(?m)^\[tasks\.([\w-]+)\]", r.read(f)))
    return names


@check(
    "DX-TASKRUNNER", DX, "Task runner with standard targets", 4, "S",
    why="One discoverable entrypoint (`make help`) with the same verbs everywhere lets humans and agents run lint/test/build without reading CI YAML.",
    detect="Root Makefile/justfile/Taskfile/package.json scripts/mise: covers setup, lint, format, test, run/build groups (4+ passes, 2+ partial). Go/Rust/.NET repos relying on the bare toolchain are partial.",
    fix="Add a root Makefile with setup, lint, format, typecheck, test, build and check targets that CI also calls.",
    ref=("Makefile", "backend/Makefile", "frontend/Makefile"),
)
def _dx_tasks(r: Repo) -> Result:
    names = _task_names(r)
    hit = [g for g, alts in GROUPS.items() if names & alts]
    if len(hit) >= 4:
        return P(f"covers {', '.join(hit)}")
    if len(hit) >= 2:
        return H(f"covers {', '.join(hit)}; missing {', '.join(set(GROUPS) - set(hit))}")
    if not names and r.stacks and set(r.stacks) <= {"go", "rust", "dotnet", "jvm"}:
        return H("only the language toolchain (go/cargo/dotnet/mvn) is available; add a Makefile/justfile so lint+format+test are discoverable")
    return F("no root task runner exposing standard verbs")


@check(
    "DX-ENV-EXAMPLE", DX, ".env.example documents configuration", 3, "S",
    why="Documents every environment variable with a safe default so setup does not depend on tribal knowledge or real secrets.",
    detect="`.env.example` / `.env.sample` / `.env.template` (any depth). Applies to services.",
    fix="Commit .env.example with every variable, safe local defaults and a comment on each; gitignore the real .env.",
    ref=".env.example",
    applies=lambda r: r.is_service,
    na="not a service/application",
)
def _dx_env(r: Repo) -> Result:
    f = r.first("**/.env.example", "**/.env.sample", "**/.env.template", "**/.env.dist", "**/env.example", "**/*.env.example")
    return P(f) if f else F("no .env.example")


def _toolchain_score(r: Repo, lang: str) -> tuple[float, str]:
    if r.glob(".tool-versions", "mise.toml", ".mise.toml"):
        return 1.0, "mise/asdf versions"
    if lang == "python":
        if r.glob("**/.python-version", "runtime.txt"):
            return 1.0, ".python-version"
        if any("requires-python" in json.dumps(d.get("project", {})) for _, d in r.pyprojects()) or "requires-python" in r.read("pyproject.toml") or "python_requires" in r.read("setup.py") + r.read("setup.cfg"):
            return 0.5, "only a requires-python floor"
    elif lang == "js":
        if r.glob("**/.nvmrc", "**/.node-version"):
            return 1.0, ".nvmrc"
        if any(isinstance(d.get("volta"), dict) for _, d in r.package_jsons()):
            return 1.0, "volta"
        if any(isinstance(d.get("engines"), dict) for _, d in r.package_jsons()):
            return 0.5, "only package.json engines"
    elif lang == "go":
        if re.search(r"(?m)^go\s+\d", r.read("go.mod")) or any(re.search(r"(?m)^go\s+\d", r.read(p)) for p in r.glob("**/go.mod")):
            return 1.0, "go directive"
    elif lang == "rust":
        if r.glob("**/rust-toolchain*"):
            return 1.0, "rust-toolchain"
        if any("rust-version" in r.read(p) for p in r.glob("**/Cargo.toml")):
            return 0.5, "only rust-version"
    elif lang == "jvm":
        if r.glob("**/.java-version", ".sdkmanrc") or any(re.search(r"JavaLanguageVersion|jvmToolchain|maven\.compiler\.(release|source|target)|<release>|java\.version|sourceCompatibility", r.read(p)) for p in r.glob("**/pom.xml", "**/build.gradle*")):
            return 1.0, "java version in build"
    elif lang == "ruby":
        if r.glob("**/.ruby-version") or any(re.search(r"(?m)^ruby\s+['\"]", r.read(p)) for p in r.glob("**/Gemfile")):
            return 1.0, ".ruby-version"
    elif lang == "php":
        if any('"php"' in r.read(p) for p in r.glob("**/composer.json")):
            return 0.5, "composer php constraint"
    elif lang == "dotnet":
        if r.glob("**/global.json"):
            return 1.0, "global.json"
    return 0.0, "no version pin"


def _langs(r: Repo) -> list[str]:
    out = []
    for s in r.stacks:
        if s in ("node", "typescript"):
            if "js" not in out:
                out.append("js")
        elif s in ("python", "go", "rust", "jvm", "ruby", "php", "dotnet"):
            out.append(s)
    return out


@check(
    "DX-TOOLCHAIN", DX, "Toolchain versions pinned", 3, "S",
    why="'Works on my machine' disappears and agents install the right runtime before running anything.",
    detect="Per detected language: .python-version, .nvmrc/.node-version, go directive, rust-toolchain, .java-version, .ruby-version, global.json or mise/.tool-versions. A version floor only is half credit.",
    fix="Commit the version file for each runtime and use it from CI (`python-version-file`, `node-version-file`).",
    ref=("backend/.python-version", "frontend/.nvmrc"),
    applies=lambda r: bool(_langs(r)),
    na="no supported language detected",
)
def _dx_toolchain(r: Repo) -> Result:
    langs = _langs(r)
    res = {lang: _toolchain_score(r, lang) for lang in langs}
    score = sum(v[0] for v in res.values()) / len(res)
    return graded(score, "; ".join(f"{k}: {v[1]}" for k, v in res.items()))


@check(
    "DX-GITIGNORE", DX, ".gitignore covers build artefacts", 2, "S",
    why="Keeps dependency folders, caches and local env files out of history and out of agent context.",
    detect=".gitignore mentions the standard artefacts for each detected stack (node_modules, __pycache__/.venv, target, bin/obj ...).",
    fix="Start from the GitHub gitignore template for your stack and add .env, coverage and tool caches.",
    ref=".gitignore",
)
def _dx_gitignore(r: Repo) -> Result:
    if not r.has(".gitignore"):
        return F("no .gitignore")
    t = r.read(".gitignore")
    need = {"python": r"__pycache__|\.venv|\*\.py\[co\]", "js": r"node_modules", "rust": r"(?m)^/?target", "jvm": r"(?m)^/?(target|build)|\.gradle", "dotnet": r"(?m)^\**/?(bin|obj)", "ruby": r"\.bundle|vendor/bundle", "go": r"(?m)^/?(bin|vendor|dist)|\*\.test|\*\.out", "php": r"vendor"}
    missing = [lang for lang in _langs(r) if lang in need and not re.search(need[lang], t)]
    if not missing:
        return P(".gitignore covers detected stacks")
    return H(f".gitignore lacks artefacts for: {', '.join(missing)}")


@check(
    "DX-GITATTRIBUTES", DX, "Line endings normalised (.gitattributes)", 1, "S",
    why="Prevents CRLF/LF churn and broken shell scripts on Windows checkouts.",
    detect=".gitattributes with `text=auto` or `eol=lf`.",
    fix="Add `* text=auto` and `*.sh text eol=lf` to .gitattributes.",
    ref=".gitattributes",
)
def _dx_attrs(r: Repo) -> Result:
    return P(".gitattributes") if r.has(".gitattributes") and re.search(r"text=auto|eol=lf|text eol", r.read(".gitattributes")) else F("no .gitattributes line-ending rules")
