"""Shared test fixtures.

Tests reach PostgreSQL through two roles, exactly like production:

* the owner role applies migrations;
* the restricted application role runs everything else.

Security tests (seller isolation, append-only ledger) are only meaningful when
they run as the restricted role, because PostgreSQL lets superusers and table
owners skip row-level security. ``restricted_role_guard`` stops the whole run
if the application connection is anything more powerful than it should be.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_APP_URL = "postgresql+psycopg://orderdesk_app:app-dev-only@127.0.0.1:5432/orderdesk_test"
DEFAULT_OWNER_URL = (
    "postgresql+psycopg://orderdesk_owner:owner-dev-only@127.0.0.1:5432/orderdesk_test"
)


def _test_database_url(variable: str, default: str) -> str:
    url = os.environ.get(variable, default)
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        raise pytest.UsageError(
            f"{variable} points at database {database!r}. Tests change and drop data, "
            "so they only run against a database whose name ends with '_test'."
        )
    return url


@pytest.fixture(scope="session")
def app_database_url() -> str:
    """URL of the restricted application role."""
    return _test_database_url("ORDERDESK_TEST_DATABASE_URL", DEFAULT_APP_URL)


@pytest.fixture(scope="session")
def owner_database_url() -> str:
    """URL of the owner role. Only migrations and test setup may use it."""
    return _test_database_url("ORDERDESK_TEST_MIGRATIONS_DATABASE_URL", DEFAULT_OWNER_URL)


@pytest.fixture(scope="session")
def alembic_config(owner_database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.attributes["database_url"] = owner_database_url
    config.attributes["configure_logging"] = False
    return config


@pytest.fixture(scope="session", autouse=True)
def migrated_database(alembic_config: Config) -> None:
    """Bring the test database to the latest schema, as the owner role."""
    command.upgrade(alembic_config, "head")


@pytest.fixture(scope="session", autouse=True)
def restricted_role_guard(
    migrated_database: None, app_database_url: str, owner_database_url: str
) -> None:
    """Abort the run unless the application connection is truly restricted."""
    problems: list[str] = []
    if make_url(app_database_url).username == make_url(owner_database_url).username:
        problems.append("the application and owner URLs use the same role")

    engine = create_engine(app_database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        r.rolname,
                        r.rolsuper,
                        r.rolbypassrls,
                        (SELECT count(*) FROM pg_class c WHERE c.relowner = r.oid) AS owned,
                        (
                            SELECT count(*)
                            FROM pg_auth_members m
                            WHERE m.member = r.oid
                        ) AS memberships
                    FROM pg_roles r
                    WHERE r.rolname = current_user
                    """
                )
            ).one()
    finally:
        engine.dispose()

    if row.rolsuper:
        problems.append(f"role {row.rolname} is a superuser")
    if row.rolbypassrls:
        problems.append(f"role {row.rolname} can bypass row-level security")
    if row.owned:
        problems.append(f"role {row.rolname} owns {row.owned} database object(s)")
    if row.memberships:
        problems.append(f"role {row.rolname} is a member of another role")

    if problems:
        pytest.exit(
            "Tests must run as the restricted application role, but " + "; ".join(problems) + ".",
            returncode=2,
        )


@pytest.fixture
async def app_engine(app_database_url: str) -> AsyncIterator[AsyncEngine]:
    """Async engine connected as the restricted application role."""
    engine = create_async_engine(app_database_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()
