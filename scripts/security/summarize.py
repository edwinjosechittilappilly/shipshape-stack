#!/usr/bin/env python3
"""Turn Trivy JSON reports into one Markdown summary and a pass/fail exit code.

Used by scripts/security/trivy-scan.sh (and usable from CI for the job summary or a PR comment).
Standard library only. Exit codes: 0 no findings, 1 findings present, 2 usage/input error.

    summarize.py --out summary.md reports/security/trivy-*.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]
MAX_ROWS = 25  # keep the summary short enough for a PR comment / job summary


def _rank(severity: str) -> int:
    return SEVERITY_ORDER.index(severity) if severity in SEVERITY_ORDER else len(SEVERITY_ORDER)


def _cell(text: Any) -> str:
    """Make a value safe inside a Markdown table cell."""
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def collect(report: dict[str, Any]) -> list[dict[str, str]]:
    """Flatten one Trivy report into rows: kind, severity, id, target, detail."""
    rows: list[dict[str, str]] = []
    for result in report.get("Results") or []:
        target = result.get("Target", "")
        for v in result.get("Vulnerabilities") or []:
            fixed = v.get("FixedVersion") or "no fix"
            rows.append(
                {
                    "kind": "vulnerability",
                    "severity": v.get("Severity", "UNKNOWN"),
                    "id": v.get("VulnerabilityID", ""),
                    "target": target,
                    "detail": f"{v.get('PkgName', '')} {v.get('InstalledVersion', '')} -> {fixed}",
                }
            )
        for m in result.get("Misconfigurations") or []:
            if m.get("Status", "FAIL") != "FAIL":
                continue
            rows.append(
                {
                    "kind": "misconfiguration",
                    "severity": m.get("Severity", "UNKNOWN"),
                    "id": m.get("ID", ""),
                    "target": target,
                    "detail": m.get("Title", ""),
                }
            )
        for s in result.get("Secrets") or []:
            rows.append(
                {
                    "kind": "secret",
                    "severity": s.get("Severity", "UNKNOWN"),
                    "id": s.get("RuleID", ""),
                    "target": f"{target}:{s.get('StartLine', '')}",
                    "detail": s.get("Title", ""),
                }
            )
    return rows


def render(sections: list[tuple[str, list[dict[str, str]]]]) -> str:
    total = sum(len(rows) for _, rows in sections)
    lines = ["## Trivy security scan", ""]
    if total == 0:
        lines.append("No HIGH/CRITICAL findings.")
    else:
        lines.append(f"**{total} finding(s)** need attention.")
    lines += ["", "| Scan | Critical | High | Other | Total |", "| --- | ---: | ---: | ---: | ---: |"]
    for name, rows in sections:
        counts = Counter(r["severity"] for r in rows)
        other = len(rows) - counts["CRITICAL"] - counts["HIGH"]
        lines.append(f"| {_cell(name)} | {counts['CRITICAL']} | {counts['HIGH']} | {other} | {len(rows)} |")
    for name, rows in sections:
        if not rows:
            continue
        rows = sorted(rows, key=lambda r: (_rank(r["severity"]), r["target"], r["id"]))
        lines += [
            "",
            f"### {_cell(name)}",
            "",
            "| Severity | Kind | ID | Target | Detail |",
            "| --- | --- | --- | --- | --- |",
        ]
        for r in rows[:MAX_ROWS]:
            lines.append(
                f"| {r['severity']} | {r['kind']} | {_cell(r['id'])} | `{_cell(r['target'])}` | {_cell(r['detail'])} |"
            )
        if len(rows) > MAX_ROWS:
            lines.append(f"\n_{len(rows) - MAX_ROWS} more not shown; see the JSON/SARIF reports._")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("reports", nargs="+", type=Path, help="Trivy JSON reports (trivy-<name>.json)")
    parser.add_argument("--out", type=Path, help="write the Markdown summary here (default: stdout)")
    args = parser.parse_args(argv)

    sections: list[tuple[str, list[dict[str, str]]]] = []
    for path in args.reports:
        try:
            report = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"summarize: cannot read {path}: {exc}", file=sys.stderr)
            return 2
        name = path.stem.removeprefix("trivy-")
        sections.append((name, collect(report)))

    markdown = render(sections)
    if args.out:
        args.out.write_text(markdown)
    else:
        sys.stdout.write(markdown)
    return 1 if any(rows for _, rows in sections) else 0


if __name__ == "__main__":
    raise SystemExit(main())
