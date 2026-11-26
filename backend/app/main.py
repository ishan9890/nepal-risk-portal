from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import admin_units, health
from app.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield                      # the app runs while we're paused here
    await engine.dispose()     # on shutdown, close database connections


app = FastAPI(
    title="Nepal Ward-Level Disaster Risk Intelligence API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(admin_units.router, prefix="/api/v1")