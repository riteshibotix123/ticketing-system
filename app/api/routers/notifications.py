from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.core.pagination import PageParams
from app.schemas.common import Page
from app.schemas.notifications import NotificationOut, UnreadCountOut
from app.services.notifications import NotificationService

router = APIRouter(tags=["notifications"])


@router.get(
    "/notifications", response_model=Page[NotificationOut], response_model_exclude_none=True
)
def list_notifications(
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    params: Annotated[PageParams, Depends()],
    unread: bool = False,
) -> Page[NotificationOut]:
    return NotificationService(db, clock).list_own(actor, unread, params)


@router.get("/notifications/unread-count", response_model=UnreadCountOut)
def unread_count(actor: CurrentActor, db: DbSession, clock: ClockDep) -> UnreadCountOut:
    return NotificationService(db, clock).unread_count(actor)


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(actor: CurrentActor, db: DbSession, clock: ClockDep) -> Response:
    NotificationService(db, clock).mark_all_read(actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/notifications/{id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(id: str, actor: CurrentActor, db: DbSession, clock: ClockDep) -> Response:
    NotificationService(db, clock).mark_read(actor, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
