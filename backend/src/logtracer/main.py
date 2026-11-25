"""FastAPI app. Each role registers its router here with a small, separate change."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from logtracer import __version__
from logtracer.api import chat, events, health, ingest, jobs, sources, suggestions, trace
from logtracer.api.analysis import router as analysis_router
from logtracer.core.config import Settings, get_settings
from logtracer.core.logpaket import ensure_from_settings
from logtracer.ingest.watcher import LogWatcher
from logtracer.services import dataset_service
from logtracer.services.ingest_service import IngestManager
from logtracer.storage.db import connect, init_schema


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Extract the log package from the LFS ZIP once if it is not there yet.
        app.state.logpaket = ensure_from_settings(settings)
        # One connection for the whole process: DuckDB allows only one writing process.
        app.state.db = connect(settings.db_path)
        init_schema(app.state.db)
        # The assistant (P3) reads and writes through the same connection.
        chat.use_connection(app.state.db)
        app.state.ingest = IngestManager(app.state.db, settings)
        if (uploaded := dataset_service.load_active(settings)) is not None:
            app.state.ingest.restore_dataset(uploaded)  # the DB holds an uploaded ZIP
        app.state.watcher = None
        if settings.watch_enabled and settings.log_root.is_dir():
            app.state.watcher = LogWatcher(settings.log_root, app.state.ingest.on_files_changed,
                                           debounce_s=settings.watch_debounce_s)
            app.state.watcher.start()
            app.state.ingest.start_rescans(settings.watch_rescan_s)
        if settings.auto_analysis:
            app.state.ingest.start_analysis(only_if_needed=True)
        try:
            yield
        finally:
            if app.state.watcher is not None:
                app.state.watcher.stop()
            app.state.ingest.stop_rescans()
            app.state.ingest.wait(timeout=30)
            chat.use_connection(None)
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

    # Routers (prefix /api). Owners: health/sources/events/ingest/suggestions = P1,
    # analysis/trace = P2, chat = P3, eval = P5.
    app.include_router(health.router, prefix="/api")
    app.include_router(sources.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    app.include_router(ingest.router, prefix="/api")
    app.include_router(suggestions.router, prefix="/api")
    app.include_router(trace.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(analysis_router, prefix="/api")
    return app


app = create_app()
