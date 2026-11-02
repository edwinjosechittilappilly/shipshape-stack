"""Declarative check registry: the data model and the `@check` decorator.

Each check is one function `evaluate(repo) -> Result` plus metadata (id, category, weight, applicability,
remediation text and the template files to copy/adapt). The check definitions live in `checks_*.py`; the
public entry point is `checks.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from repo_context import Repo

PASS, PARTIAL, FAIL, NA = "pass", "partial", "fail", "na"
POINTS = {PASS: 1.0, PARTIAL: 0.5, FAIL: 0.0}
EFFORT_ORDER = {"S": 0, "M": 1, "L": 2}


@dataclass(frozen=True)
class Result:
    status: str
    evidence: str


def P(evidence: str) -> Result:
    return Result(PASS, evidence)


def H(evidence: str) -> Result:
    return Result(PARTIAL, evidence)


def F(evidence: str) -> Result:
    return Result(FAIL, evidence)


def graded(score: float, evidence: str, pass_at: float = 1.0) -> Result:
    """Map a 0..1 fraction to pass / partial / fail (pass only at `pass_at`, partial for any positive value)."""
    if score >= pass_at - 1e-9:
        return P(evidence)
    if score > 0:
        return H(evidence)
    return F(evidence)


def from_reach(reach: str | None, what: str) -> Result:
    """Translate `Repo.ci_reach()` into a result: enforced in CI > configured but not run by CI > absent."""
    if reach == "ci":
        return P(f"{what}: run by CI")
    if reach == "tasks":
        return P(f"{what}: run by CI via the task runner/scripts")
    if reach == "config-only":
        return H(f"{what}: configured locally but CI does not appear to run it")
    return F(f"no {what} found in CI or in the task runner CI calls")


def always(_: Repo) -> bool:
    return True


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    weight: int
    rationale: str


@dataclass(frozen=True)
class Check:
    id: str
    category: str
    title: str
    weight: int
    effort: str  # S: <1h, one file; M: a few hours, several files; L: days, needs design
    why: str  # why it matters for humans AND agents
    detect: str  # how the scanner decides
    remediation: str
    template_ref: tuple[str, ...]
    evaluate: Callable[[Repo], Result]
    applies: Callable[[Repo], bool] = always
    na_reason: str = ""


REGISTRY: list[Check] = []


def check(
    id: str,
    category: str,
    title: str,
    weight: int,
    effort: str,
    *,
    why: str,
    detect: str,
    fix: str,
    ref: tuple[str, ...] | str = (),
    applies: Callable[[Repo], bool] = always,
    na: str = "",
):
    if effort not in EFFORT_ORDER:
        raise ValueError(f"{id}: effort must be S, M or L")
    refs = (ref,) if isinstance(ref, str) else tuple(ref)

    def deco(fn: Callable[[Repo], Result]):
        if any(c.id == id for c in REGISTRY):
            raise ValueError(f"duplicate check id {id}")
        REGISTRY.append(Check(id, category, title, weight, effort, why, detect, fix, refs, fn, applies, na))
        return fn

    return deco
