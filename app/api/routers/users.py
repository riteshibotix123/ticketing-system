from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.core.enums import AccountState, Role
from app.core.pagination import PageParams
from app.schemas.common import Page, UserRef
from app.schemas.users import DeactivateBody, DeactivationResult, UpdateRolesBody, UserListItem
from app.services.users import UserService

QUERY_MAX_LENGTH = 200

router = APIRouter(tags=["users"])


@router.get("/users", response_model=Page[UserListItem])
def list_users(
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    params: Annotated[PageParams, Depends()],
    q: Annotated[str | None, Query(max_length=QUERY_MAX_LENGTH)] = None,
    role: Role | None = None,
    state: AccountState | None = None,
    department_id: Annotated[str | None, Query(max_length=6)] = None,
) -> Page[UserListItem]:
    return UserService(db, clock).list_users(actor, q, role, state, department_id, params)


@router.get("/users/lookup", response_model=list[UserRef])
def lookup_users(
    _actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    q: Annotated[str, Query(max_length=QUERY_MAX_LENGTH)] = "",
) -> list[UserRef]:
    return UserService(db, clock).lookup(q)


@router.get("/departments/{id}/members", response_model=list[UserRef])
def department_members(
    id: str, _actor: CurrentActor, db: DbSession, clock: ClockDep
) -> list[UserRef]:
    return UserService(db, clock).department_members(id)


@router.patch("/users/{id}/roles", response_model=UserListItem)
def update_roles(
    id: str, body: UpdateRolesBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> UserListItem:
    return UserService(db, clock).update_roles(actor, id, body.spoke_departments, body.reason)


@router.post("/users/{id}/deactivate", response_model=DeactivationResult)
def deactivate_user(
    id: str, body: DeactivateBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> DeactivationResult:
    return UserService(db, clock).deactivate(actor, id, body.reason)


@router.post("/users/{id}/activate", response_model=UserListItem)
def activate_user(id: str, actor: CurrentActor, db: DbSession, clock: ClockDep) -> UserListItem:
    return UserService(db, clock).activate(actor, id)
