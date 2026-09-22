"""
FastAPI application entrypoint.

Wires together the pieces built under app/: creates the MySQL tables on
startup if they don't exist yet (raw PyMySQL, no ORM - see app/db.py),
enables CORS so the static Frontend/ pages can call this API from a
browser, and mounts the router defined in app/api/routes.py.

Run locally:
    uvicorn main:app --reload --port 8000
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings
from app.db import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notification_app")

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    logger.info("Database initialized (mysql: %s@%s:%s/%s)", settings.mysql_user, settings.mysql_host, settings.mysql_port, settings.mysql_database)
    for channel, configured in (
        ("teams", settings.teams_configured),
        ("slack", settings.slack_configured),
        ("email", settings.email_configured),
    ):
        logger.info("Channel %-6s -> %s", channel, "real provider" if configured else "MockProvider (no credentials set)")
    yield


app = FastAPI(
    title="Notification Management Application",
    description="Teams / Email / Slack notification service (FastAPI + MySQL).",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
