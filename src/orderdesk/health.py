"""Health check used by Docker, CI and uptime monitoring."""

import logging
from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

router = APIRouter()


class Health(BaseModel):
    status: Literal["ok", "unavailable"]


@router.get(
    "/healthz",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": Health}},
)
async def healthz(request: Request, response: Response) -> Health:
    """Report whether the service can reach its database."""
    engine: AsyncEngine = request.app.state.engine
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as error:
        logger.warning("Health check failed: database unreachable (%s)", type(error).__name__)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Health(status="unavailable")
    return Health(status="ok")
