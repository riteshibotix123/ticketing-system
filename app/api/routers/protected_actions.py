from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.core.enums import ProtectedActionStatus
from app.core.pagination import PageParams
from app.schemas.common import Page
from app.schemas.users import (
    CreateProtectedActionBody,
    ProtectedActionOut,
    RejectProtectedActionBody,
)
from app.services.protected_actions import ProtectedActionService

router = APIRouter(tags=["protected-actions"])


@router.get(
    "/protected-actions",
    response_model=Page[ProtectedActionOut],
    response_model_exclude_none=True,
)
def list_protected_actions(
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    params: Annotated[PageParams, Depends()],
    status_filter: Annotated[ProtectedActionStatus | None, Query(alias="status")] = None,
) -> Page[ProtectedActionOut]:
    return ProtectedActionService(db, clock).list_actions(actor, status_filter, params)


@router.post(
    "/protected-actions", response_model=ProtectedActionOut, response_model_exclude_none=True
)
def create_protected_action(
    body: CreateProtectedActionBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> ProtectedActionOut:
    return ProtectedActionService(db, clock).create(
        actor, body.kind, body.target_user_id, body.reason
    )


@router.post(
    "/protected-actions/{id}/approve",
    response_model=ProtectedActionOut,
    response_model_exclude_none=True,
)
def approve_protected_action(
    id: str, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> ProtectedActionOut:
    return ProtectedActionService(db, clock).approve(actor, id)


@router.post(
    "/protected-actions/{id}/reject",
    response_model=ProtectedActionOut,
    response_model_exclude_none=True,
)
def reject_protected_action(
    id: str,
    body: RejectProtectedActionBody,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> ProtectedActionOut:
    return ProtectedActionService(db, clock).reject(actor, id, body.reason)
