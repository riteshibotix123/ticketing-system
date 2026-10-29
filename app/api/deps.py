from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.errors import forbidden, unauthenticated
from app.core.security import InvalidAccessToken, decode_access_token
from app.policy import Actor
from app.services.me import MeService

BEARER_PREFIX = "bearer "

DbSession = Annotated[Session, Depends(get_db, scope="function")]
ClockDep = Annotated[Clock, Depends(get_clock)]


def get_app_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, Settings):
        return settings
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization")
    if header is None or not header.lower().startswith(BEARER_PREFIX):
        return None
    token = header[len(BEARER_PREFIX) :].strip()
    return token or None


def get_actor(request: Request, db: DbSession, clock: ClockDep, settings: SettingsDep) -> Actor:
    token = _bearer_token(request)
    if token is None:
        raise unauthenticated()
    try:
        user_id = decode_access_token(token, clock.now(), settings)
    except InvalidAccessToken as exc:
        raise unauthenticated() from exc
    actor = MeService(db).load_active_actor(user_id)
    if actor is None:
        raise unauthenticated()
    request.state.user_id = str(actor.id)
    return actor


CurrentActor = Annotated[Actor, Depends(get_actor)]


def require_allowed_origin(request: Request, settings: SettingsDep) -> None:
    origin = request.headers.get("Origin")
    if origin is not None and origin not in settings.cors_origins:
        raise forbidden()
