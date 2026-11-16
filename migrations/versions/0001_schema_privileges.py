"""Lock down the public schema for the application role.

Nobody gets access to the schema by default. The application role may look
objects up (USAGE) but cannot create any. Later migrations grant it privileges
table by table, so every permission the app has is written down in a migration.

Revision ID: 0001
Revises:
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

from orderdesk.db import APP_ROLE

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    op.execute("GRANT USAGE ON SCHEMA public TO PUBLIC")
