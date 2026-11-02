"""Shared pytest hooks."""

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # Anything under tests/integration/ is an integration test, without per-file boilerplate.
    # (`-m 'not integration'` in pyproject then keeps the default run fast and DB-free.)
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)
