"""The application role must be too weak to defeat the database's protections."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

from orderdesk.db import APP_ROLE


async def test_tests_connect_as_the_application_role(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as connection:
        current_user = (await connection.execute(text("SELECT current_user"))).scalar_one()

    assert current_user == APP_ROLE


async def test_application_role_has_no_special_powers(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole
                    FROM pg_roles
                    WHERE rolname = current_user
                    """
                )
            )
        ).one()

    assert not row.rolsuper
    assert not row.rolbypassrls
    assert not row.rolcreatedb
    assert not row.rolcreaterole


async def test_application_role_owns_no_database_objects(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as connection:
        owned = (
            await connection.execute(
                text(
                    """
                    SELECT count(*)
                    FROM pg_class c
                    JOIN pg_roles r ON r.oid = c.relowner
                    WHERE r.rolname = current_user
                    """
                )
            )
        ).scalar_one()

    assert owned == 0


async def test_application_role_cannot_create_tables(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as connection:
        with pytest.raises(ProgrammingError, match="permission denied"):
            await connection.execute(text("CREATE TABLE should_not_exist (id integer)"))


async def test_application_role_cannot_read_migration_bookkeeping(
    app_engine: AsyncEngine,
) -> None:
    async with app_engine.connect() as connection:
        with pytest.raises(ProgrammingError, match="permission denied"):
            await connection.execute(text("SELECT version_num FROM alembic_version"))
