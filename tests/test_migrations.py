from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migrations_have_a_single_head(alembic_config: Config) -> None:
    heads = ScriptDirectory.from_config(alembic_config).get_heads()

    assert len(heads) == 1


def test_migrations_downgrade_to_base_and_upgrade_again(alembic_config: Config) -> None:
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


def test_models_and_migrations_are_in_sync(alembic_config: Config) -> None:
    # Raises if the SQLAlchemy models describe a schema the migrations do not create.
    command.check(alembic_config)
