"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from orderdesk.config import Settings
from orderdesk.db import create_engine
from orderdesk.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = create_engine(settings)
    app.state.engine = engine
    try:
        yield
    finally:
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Tests pass their own settings. In production the settings come from
    environment variables.
    """
    # The service has no public HTTP API, so the interactive docs are off.
    app = FastAPI(
        title="Order Desk",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings if settings is not None else Settings()
    app.include_router(health_router)
    return app
