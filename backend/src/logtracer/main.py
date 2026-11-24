"""FastAPI app. Each role registers its router here with a small, separate change."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from logtracer import __version__
from logtracer.api import chat, health
from logtracer.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Log Tracer API",
    version=__version__,
    description="Cross-system log ingest, analysis and AI assistant (MAIT Makeathon 2026).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers (prefix /api). Owners: health/ingest/events = P1, analysis = P2, chat = P3, eval = P5.
app.include_router(health.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
