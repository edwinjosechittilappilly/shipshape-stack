#!/usr/bin/env python3
"""repo-audit: score a repository against the practices embodied by the best-practice template.

Pure static analysis of the filesystem: no network, no execution of target code, standard library only
(Python >= 3.11). Usage:

    python3 audit.py <repo> [--format text|markdown|json] [--min-score N] [--category NAME]... [--template-url URL]

Exit codes: 0 ok, 1 score below --min-score, 2 usage error (bad path / unknown category).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

if sys.version_info < (3, 11):  # noqa: UP036 - users run this with whatever python3 they have (macOS ships 3.9)
    sys.exit(f"repo-audit needs Python >= 3.11 (found {sys.version.split()[0]}). Try: uv run --python 3.12 python {sys.argv[0]} ...")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import checks  # noqa: E402
from registry import EFFORT_ORDER, NA, POINTS  # noqa: E402
from repo_context import Repo  # noqa: E402

SCHEMA_VERSION = 1
DEFAULT_TEMPLATE_URL = "https://github.com/edwinjosechittilappilly/shipshape-stack/blob/main"
GRADES = ((90, "A"), (80, "B"), (70, "C"), (60, "D"))

# Things no static scan can establish; the agent must verify them (see references/rubric.md, "Qualitative pass").
MANUAL_REVIEW = (
    "README: follow it literally on a clean checkout; does a newcomer reach a running app and a green test run?",
    "Tests: open 3-5 tests; do they assert behaviour (outputs, state, HTTP responses) rather than only that code runs?",
    "CI: is the default branch actually green? (`gh run list --branch <default> --limit 10`, `gh run view <id> --log-failed`)",
    "Branch protection: is the aggregate CI check required and are force-pushes blocked? (`gh api repos/{owner}/{repo}/branches/<default>/protection`)",
    "Docs currency: do documented commands, paths and versions still exist? Is anything contradicted by the code?",
    "Security settings: are secret scanning, push protection, Dependabot alerts and CodeQL default setup enabled in repository settings?",
    "Agent instructions: do they match reality (commands work, boundaries sensible) and stay concise?",
)


def grade_for(score: float) -> str:
    for floor, letter in GRADES:
        if score >= floor:
            return letter
    return "F"


def _r1(x: float) -> float:
    return round(x + 1e-9, 1)


def run_audit(repo: Repo, template_url: str = DEFAULT_TEMPLATE_URL, categories: list[str] | None = None) -> dict:
    start = time.perf_counter()
    base = template_url.rstrip("/")
    wanted = {c for c in categories} if categories else {c.id for c in checks.CATEGORIES}

    results = []
    for chk in checks.all_checks():
        if chk.category not in wanted:
            continue
        status, evidence = NA, chk.na_reason or "not applicable"
        try:
            if chk.applies(repo):
                res = chk.evaluate(repo)
                status, evidence = res.status, res.evidence
        except Exception as exc:  # a broken check must never take the whole audit down
            status, evidence = NA, f"internal error in check ({type(exc).__name__}: {exc}); excluded from scoring"
        results.append({"chk": chk, "status": status, "evidence": evidence})

    cat_rows = []
    for cat in checks.CATEGORIES:
        if cat.id not in wanted:
            continue
        rows = [x for x in results if x["chk"].category == cat.id]
        applicable = [x for x in rows if x["status"] != NA]
        den = sum(x["chk"].weight for x in applicable)
        num = sum(x["chk"].weight * POINTS[x["status"]] for x in applicable)
        cat_rows.append({"cat": cat, "rows": rows, "den": den, "pct": (100.0 * num / den) if den else None})

    live = [c for c in cat_rows if c["pct"] is not None]
    total_w = sum(c["cat"].weight for c in live)
    overall = sum(c["cat"].weight * c["pct"] for c in live) / total_w if total_w else 0.0

    for c in cat_rows:
        for x in c["rows"]:
            if x["status"] == NA or not total_w:
                x["gain"] = 0.0
            else:
                x["gain"] = (c["cat"].weight / total_w) * (x["chk"].weight / c["den"]) * (1 - POINTS[x["status"]]) * 100

    def fixable(x):
        return x["status"] in ("partial", "fail")

    ordered = sorted((x for x in results if fixable(x)), key=lambda x: (-x["gain"], EFFORT_ORDER[x["chk"].effort], x["chk"].id))
    top = ordered[:10]
    quick = [x for x in ordered if x["chk"].effort == "S"][:8]

    def check_json(x):
        chk = x["chk"]
        return {
            "id": chk.id,
            "category": chk.category,
            "title": chk.title,
            "weight": chk.weight,
            "effort": chk.effort,
            "status": x["status"],
            "points": None if x["status"] == NA else POINTS[x["status"]],
            "evidence": x["evidence"],
            "remediation": chk.remediation,
            "template_refs": [{"path": p, "url": f"{base}/{p}"} for p in chk.template_ref],
            "gain": round(x["gain"], 2),
        }

    counts = {"total": len(results)}
    for st in ("pass", "partial", "fail", "na"):
        counts[st] = sum(1 for x in results if x["status"] == st)
    counts["applicable"] = counts["total"] - counts["na"]

    scope = "all" if wanted == {c.id for c in checks.CATEGORIES} else ",".join(sorted(wanted))
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "repo-audit",
        "scope": scope,
        "repo": {
            "name": repo.name,
            "path": repo.root,
            "stacks": repo.stacks,
            "flags": {
                "frontend": repo.frontend,
                "react": repo.react,
                "service": repo.is_service,
                "monorepo": repo.monorepo,
                "github_actions": bool(repo.workflows()),
                "other_ci": repo.other_ci(),
            },
            "files_scanned": len(repo.files),
            "listing": repo.listing,
            "truncated": repo.truncated,
        },
        "template_url": base,
        "score": {"overall": _r1(overall), "grade": grade_for(overall), "checks": counts},
        "categories": [
            {
                "id": c["cat"].id,
                "name": c["cat"].name,
                "weight": c["cat"].weight,
                "applicable": c["pct"] is not None,
                "score": None if c["pct"] is None else _r1(c["pct"]),
                "grade": None if c["pct"] is None else grade_for(c["pct"]),
                "rationale": c["cat"].rationale,
            }
            for c in cat_rows
        ],
        "checks": [check_json(x) for c in cat_rows for x in c["rows"]],
        "top_fixes": [check_json(x)["id"] for x in top],
        "quick_wins": [check_json(x)["id"] for x in quick],
        "manual_review": list(MANUAL_REVIEW),
        "elapsed_seconds": round(time.perf_counter() - start + getattr(repo, "walk_seconds", 0.0), 3),
    }


# ----------------------------------------------------------------------------------------------------------------------
# Renderers
# ----------------------------------------------------------------------------------------------------------------------
STATUS_LABEL = {"pass": "PASS", "partial": "PARTIAL", "fail": "FAIL", "na": "N/A"}


def _by_id(report: dict) -> dict:
    return {c["id"]: c for c in report["checks"]}


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_text(report: dict) -> str:
    s, repo = report["score"], report["repo"]
    out = [
        f"repo-audit: {repo['name']}  (stacks: {', '.join(repo['stacks']) or 'none detected'})",
        f"Overall {s['overall']:.1f}%  grade {s['grade']}   "
        f"[{s['checks']['pass']} pass, {s['checks']['partial']} partial, {s['checks']['fail']} fail, {s['checks']['na']} n/a]",
        "",
        f"{'Category':<32}{'Weight':>7}{'Score':>8}  Grade",
    ]
    for c in report["categories"]:
        score = "n/a" if c["score"] is None else f"{c['score']:.1f}%"
        out.append(f"{c['name']:<32}{c['weight']:>7}{score:>8}  {c['grade'] or '-'}")
    chk = _by_id(report)
    out += ["", "Top fixes (highest score gain first):"]
    for i, cid in enumerate(report["top_fixes"], 1):
        c = chk[cid]
        out.append(f"{i:>3}. [{c['id']}] +{c['gain']:.1f} pts, effort {c['effort']}: {c['title']}")
        out.append(f"       found: {c['evidence']}")
        out.append(f"       fix:   {c['remediation']}")
    if not report["top_fixes"]:
        out.append("  (none: every applicable check passes)")
    out += ["", "Quick wins (effort S): " + (", ".join(report["quick_wins"]) or "none")]
    return "\n".join(out) + "\n"


def render_markdown(report: dict) -> str:
    s, repo = report["score"], report["repo"]
    chk = _by_id(report)
    flags = [k.replace("_", " ") for k, v in repo["flags"].items() if v]
    out = [
        f"# Repository audit: {repo['name']}",
        "",
        f"**Overall score: {s['overall']:.1f}% (grade {s['grade']})**  ",
        f"Detected stacks: {', '.join(repo['stacks']) or 'none'}" + (f" · traits: {', '.join(flags)}" if flags else "") + "  ",
        f"Checks: {s['checks']['pass']} pass · {s['checks']['partial']} partial · {s['checks']['fail']} fail · {s['checks']['na']} not applicable "
        f"({s['checks']['applicable']} scored of {s['checks']['total']})  ",
        f"Files scanned: {repo['files_scanned']}" + (" (truncated)" if repo["truncated"] else "") + f" · scope: {report['scope']}",
        "",
        "## Scorecard",
        "",
        "| Category | Weight | Score | Grade | Pass / Partial / Fail |",
        "| --- | ---: | ---: | :---: | :---: |",
    ]
    for c in report["categories"]:
        rows = [x for x in report["checks"] if x["category"] == c["id"] and x["status"] != "na"]
        tally = " / ".join(str(sum(1 for x in rows if x["status"] == st)) for st in ("pass", "partial", "fail"))
        score = "n/a (excluded)" if c["score"] is None else f"{c['score']:.1f}%"
        out.append(f"| {c['name']} | {c['weight']} | {score} | {c['grade'] or '-'} | {tally} |")
    out += ["", "## Top fixes (by score impact, then effort)", ""]
    if report["top_fixes"]:
        out += ["| # | Check | Status | Gain | Effort | Fix |", "| ---: | --- | :---: | ---: | :---: | --- |"]
        for i, cid in enumerate(report["top_fixes"], 1):
            c = chk[cid]
            out.append(f"| {i} | `{c['id']}` {_cell(c['title'])} | {STATUS_LABEL[c['status']]} | +{c['gain']:.1f} | {c['effort']} | {_cell(c['remediation'])} |")
    else:
        out.append("Every applicable check passes.")
    out += ["", "## Quick wins (effort S)", ""]
    out += [f"- `{cid}` (+{chk[cid]['gain']:.1f}): {chk[cid]['remediation']}" for cid in report["quick_wins"]] or ["- none"]
    out += ["", "## Findings by category", ""]
    for c in report["categories"]:
        score = "excluded: not applicable" if c["score"] is None else f"{c['score']:.1f}%"
        out += [f"### {c['name']} ({score}, weight {c['weight']})", ""]
        rows = [x for x in report["checks"] if x["category"] == c["id"]]
        out += ["| Check | Status | Evidence |", "| --- | :---: | --- |"]
        for x in rows:
            out.append(f"| `{x['id']}` {_cell(x['title'])} | {STATUS_LABEL[x['status']]} | {_cell(x['evidence'])} |")
        todo = [x for x in rows if x["status"] in ("partial", "fail")]
        if todo:
            out += ["", "Remediation:", ""]
            for x in todo:
                refs = ", ".join(f"[{r['path']}]({r['url']})" for r in x["template_refs"])
                out.append(f"- **{x['id']}** (effort {x['effort']}): {x['remediation']}" + (f" Template: {refs}" if refs else ""))
        out.append("")
    out += ["## Needs judgement (not scored)", ""] + [f"- {m}" for m in report["manual_review"]]
    out += ["", f"_Generated by repo-audit (schema v{report['schema_version']}); static analysis only, see references/rubric.md._", ""]
    return "\n".join(out)


def render_rubric(template_url: str = DEFAULT_TEMPLATE_URL) -> str:
    """Markdown catalogue of every check; embedded verbatim in references/rubric.md (a test keeps them in sync)."""
    base = template_url.rstrip("/")
    out: list[str] = []
    for cat in checks.CATEGORIES:
        out += [f"### {cat.name} (weight {cat.weight})", "", f"*{cat.rationale}*", ""]
        for c in (x for x in checks.all_checks() if x.category == cat.id):
            applies = f"N/A when: {c.na_reason}" if c.na_reason else "always applies"
            out += [
                f"#### `{c.id}` {c.title}",
                "",
                f"Weight {c.weight} · effort {c.effort} · {applies}",
                "",
                f"- **Why it matters (humans and agents):** {c.why}",
                f"- **How it is detected:** {c.detect}",
                f"- **How to fix:** {c.remediation}",
                "- **Template reference:** " + ", ".join(f"[`{p}`]({base}/{p})" for p in c.template_ref),
                "",
            ]
    return "\n".join(out).rstrip() + "\n"


def render(report: dict, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(report, indent=2) + "\n"
    return render_markdown(report) if fmt == "markdown" else render_text(report)


# ----------------------------------------------------------------------------------------------------------------------
def resolve_categories(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    known = {c.id: c for c in checks.CATEGORIES}
    out: list[str] = []
    for raw in values:
        for part in raw.split(","):
            key = part.strip().lower()
            if not key:
                continue
            hit = [cid for cid, c in known.items() if key == cid or key == c.name.lower() or c.name.lower().startswith(key)]
            if len(hit) != 1:
                raise ValueError(f"unknown category '{part}'. Valid: {', '.join(known)}")
            out.append(hit[0])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Score a repository against the best-practice template (static analysis, no network).")
    ap.add_argument("repo", nargs="?", default=".", help="path to the repository root (default: .)")
    ap.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    ap.add_argument("--min-score", type=float, default=None, metavar="N", help="exit 1 when the overall score is below N (0-100)")
    ap.add_argument("--category", action="append", metavar="NAME", help="limit to a category id or name (repeatable or comma separated)")
    ap.add_argument("--template-url", default=DEFAULT_TEMPLATE_URL, help="base URL for template links (default: %(default)s)")
    ap.add_argument("--no-git", action="store_true", help="plain directory walk even inside a git work tree (default there: git ls-files)")
    ap.add_argument("--dump-rubric", action="store_true", help="print the per-check rubric as Markdown and exit")
    ap.add_argument("--list-checks", action="store_true", help="print the check catalogue (id, category, weight, title) and exit")
    args = ap.parse_args(argv)

    if args.dump_rubric:
        sys.stdout.write(render_rubric(args.template_url))
        return 0
    if args.list_checks:
        for c in checks.all_checks():
            print(f"{c.id:<22}{c.category:<11}w{c.weight}  {c.effort}  {c.title}")
        return 0
    if not os.path.isdir(args.repo):
        print(f"error: not a directory: {args.repo}", file=sys.stderr)
        return 2
    try:
        cats = resolve_categories(args.category)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    t0 = time.perf_counter()
    repo = Repo(args.repo, use_git=not args.no_git)
    repo.walk_seconds = time.perf_counter() - t0  # type: ignore[attr-defined]
    report = run_audit(repo, args.template_url, cats)
    sys.stdout.write(render(report, args.format))
    if args.min_score is not None and report["score"]["overall"] < args.min_score:
        print(f"repo-audit: score {report['score']['overall']:.1f} is below --min-score {args.min_score:g}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
