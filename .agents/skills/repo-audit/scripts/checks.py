"""Public entry point of the check registry.

Importing this module registers every check (definitions live in `checks_foundation`, `checks_pipeline` and
`checks_platform`) and exposes the category table. Category weights sum to 100.
"""

from __future__ import annotations

import checks_foundation  # noqa: F401  (registers checks on import)
import checks_pipeline  # noqa: F401
import checks_platform  # noqa: F401
from registry import REGISTRY, Category, Check

CATEGORIES: tuple[Category, ...] = (
    Category("docs", "Documentation & onboarding", 10,
             "A newcomer's first hour decides whether they contribute. Cheap to fix, but it is table stakes rather than a safety property, so it is not weighted highest."),
    Category("agent", "Agent readiness", 12,
             "The multiplier for AI-assisted work: instructions, skills, hooks and agent-shaped issues turn an agent from a guesser into a contributor that follows your process."),
    Category("ci", "CI/CD", 16,
             "CI is the objective gate that every other practice (tests, lint, security) is enforced through; without a trustworthy, single required check nothing else is reliable."),
    Category("quality", "Code quality", 12,
             "Linters, formatters, type checkers and lockfiles remove whole classes of review comments and make results reproducible."),
    Category("testing", "Testing", 14,
             "Tests are the executable definition of correct behaviour and the main way agents verify their own work."),
    Category("security", "Security & supply chain", 14,
             "One leaked secret or vulnerable dependency outweighs many style wins; this category is weighted high because failures are costly and mostly preventable with config."),
    Category("hygiene", "PR & issue hygiene", 6,
             "Templates, labels and PR checks make the review/triage loop fast and automatable; important for agents, smaller direct risk."),
    Category("containers", "Containers & deployment", 8,
             "Hardened images and declared deployments make 'works in CI' mean 'works in production'. Not applicable to libraries without deployables."),
    Category("dx", "Developer experience", 4,
             "Task runner, env template and pinned toolchains make setup one command; small weight because the checks are few and quick to satisfy."),
    Category("frontend", "Frontend health", 4,
             "React/JS UI specific tooling (React Doctor, a11y, Playwright, strict TS). Excluded entirely when no UI framework is detected."),
)

assert sum(c.weight for c in CATEGORIES) == 100, "category weights must sum to 100"
_IDS = {c.id for c in CATEGORIES}
for _c in REGISTRY:
    assert _c.category in _IDS, f"{_c.id}: unknown category {_c.category}"


def all_checks() -> list[Check]:
    return list(REGISTRY)


def category_by_id(cid: str) -> Category:
    return next(c for c in CATEGORIES if c.id == cid)
