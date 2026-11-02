"""Probes. Liveness never touches the DB (a DB outage must not restart the pod); readiness does."""

import logging
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import SessionDep

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


class Health(BaseModel):
    status: Literal["ok"]


class Readiness(BaseModel):
    status: Literal["ready", "unavailable"]


@router.get("/healthz")
def healthz() -> Health:
    return Health(status="ok")


@router.get("/readyz", responses={503: {"model": Readiness}})
def readyz(session: SessionDep, response: Response) -> Readiness:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("readiness check failed: database unreachable", exc_info=True)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Readiness(status="unavailable")
    return Readiness(status="ready")
