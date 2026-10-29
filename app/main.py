from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.routers import (
    admins,
    attachments,
    audit,
    auth,
    calendar,
    categories,
    confidential_grants,
    config,
    dashboards,
    departments,
    exports,
    health,
    notifications,
    policy,
    preferences,
    protected_actions,
    reports,
    saved_views,
    signup,
    ticket_comments,
    ticket_workflow,
    tickets,
    users,
)
from app.core.config import Environment, Settings, get_settings
from app.core.db import engine
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.request_context import RequestContextMiddleware
from app.core.security_headers import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.services.handlers import register_all

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings if settings is not None else get_settings()
    if resolved.env is not Environment.TEST:
        configure_logging()
    app = FastAPI(
        title="Ibotix Ticketing API",
        version="1.1.0",
        docs_url=None if resolved.env is Environment.PROD else "/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(BodySizeLimitMiddleware, max_upload_bytes=resolved.max_upload_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    register_all()
    app.include_router(health.router)
    api = APIRouter(prefix=API_PREFIX)
    api.include_router(config.router)
    api.include_router(auth.router)
    api.include_router(signup.router)
    api.include_router(users.router)
    api.include_router(admins.router)
    api.include_router(protected_actions.router)
    api.include_router(departments.router)
    api.include_router(categories.router)
    api.include_router(confidential_grants.router)
    api.include_router(policy.router)
    api.include_router(calendar.router)
    api.include_router(tickets.router)
    api.include_router(ticket_workflow.router)
    api.include_router(ticket_comments.router)
    api.include_router(attachments.router)
    api.include_router(notifications.router)
    api.include_router(preferences.router)
    api.include_router(audit.router)
    api.include_router(dashboards.router)
    api.include_router(reports.router)
    api.include_router(exports.router)
    api.include_router(saved_views.router)
    app.include_router(api)
    return app


app = create_app()
