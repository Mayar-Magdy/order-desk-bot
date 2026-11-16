"""Application settings, read from environment variables.

The application only ever receives the connection URL of the restricted
database role. The owner role that runs migrations is configured separately
(see ``migrations/env.py``) so the running app never holds its credentials.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ORDERDESK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        description=(
            "SQLAlchemy URL for the restricted application role, "
            "for example postgresql+psycopg://orderdesk_app:...@db:5432/orderdesk"
        ),
    )
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
