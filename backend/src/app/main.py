"""Application factory. Run with `uvicorn app.main:create_app --factory`."""

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.config import Settings, get_settings
from app.db import create_db_engine, create_session_factory
from app.log_config import configure_logging
from app.service import ItemNotFoundError

logger = logging.getLogger("app.access")
_QUIET_PATHS = frozenset(
    {"/healthz", "/readyz"}
)  # probes fire every few seconds; keep them at DEBUG


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    engine = create_db_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(title="Items API", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = create_session_factory(engine)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def access_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        level = logging.DEBUG if request.url.path in _QUIET_PATHS else logging.INFO
        logger.log(
            level,
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response

    @app.exception_handler(ItemNotFoundError)
    async def item_not_found(_: Request, exc: ItemNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)

    app.include_router(api_router)
    return app
