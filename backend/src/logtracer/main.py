"""FastAPI app. Each role registers its router here with a small, separate change."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from logtracer import __version__
from logtracer.api import events, health, sources
from logtracer.core.config import Settings, get_settings
from logtracer.storage.db import connect, init_schema


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # One connection for the whole process: DuckDB allows only one writing process.
        app.state.db = connect(settings.db_path)
        init_schema(app.state.db)
        try:
            yield
        finally:
            app.state.db.close()

    app = FastAPI(
        title="Log Tracer API",
        version=__version__,
        description="Cross-system log ingest, analysis and AI assistant (MAIT Makeathon 2026).",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers (prefix /api). Owners: health/sources/events/ingest = P1, analysis = P2,
    # chat = P3, eval = P5.
    app.include_router(health.router, prefix="/api")
    app.include_router(sources.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    return app


app = create_app()
