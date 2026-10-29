from fastapi import APIRouter

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.schemas.users import PromoteAdminBody, UserListItem
from app.services.users import UserService

router = APIRouter(tags=["admins"])


@router.get("/admins", response_model=list[UserListItem])
def list_admins(actor: CurrentActor, db: DbSession, clock: ClockDep) -> list[UserListItem]:
    return UserService(db, clock).list_admins(actor)


@router.post("/admins", response_model=UserListItem)
def promote_admin(
    body: PromoteAdminBody, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> UserListItem:
    return UserService(db, clock).promote_admin(actor, body.user_id)


@router.delete("/admins/{user_id}", response_model=UserListItem)
def demote_admin(user_id: str, actor: CurrentActor, db: DbSession, clock: ClockDep) -> UserListItem:
    return UserService(db, clock).demote_admin(actor, user_id)
