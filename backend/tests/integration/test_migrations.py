"""The migrations are the schema's source of truth in production; verify them directly."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.models import Base
from tests.integration.conftest import alembic_config, temporary_database


def test_models_and_migrations_do_not_drift() -> None:
    with temporary_database() as url:
        command.upgrade(alembic_config(url), "head")
        engine = create_engine(url)
        try:
            with engine.connect() as conn:
                diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        finally:
            engine.dispose()
    assert diff == [], f"models.py and migrations/ disagree; add a migration: {diff}"


def test_upgrade_then_downgrade_round_trips() -> None:
    with temporary_database() as url:
        config = alembic_config(url)
        engine = create_engine(url)
        try:
            command.upgrade(config, "head")
            assert "items" in inspect(engine).get_table_names()
            command.downgrade(config, "base")
            assert "items" not in inspect(engine).get_table_names()
            command.upgrade(config, "head")
            assert "items" in inspect(engine).get_table_names()
        finally:
            engine.dispose()
