import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AccountState
from app.models.identity import User
from app.models.org import SpokeAssignment
from app.policy import Actor


def load_actor(session: Session, user_id: uuid.UUID) -> Actor | None:
    user = session.get(User, user_id)
    if user is None or user.state is not AccountState.ACTIVE:
        return None
    spoke_departments = session.scalars(
        select(SpokeAssignment.department_id).where(
            SpokeAssignment.user_id == user.id, SpokeAssignment.revoked_at.is_(None)
        )
    )
    return Actor(
        id=user.id,
        global_role=user.global_role,
        department_id=user.home_department_id,
        spoke_department_ids=frozenset(spoke_departments),
        name=user.name,
        email=user.email,
    )
