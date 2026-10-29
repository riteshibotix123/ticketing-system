import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AccountState
from app.models.identity import User
from app.models.org import SpokeAssignment
from app.policy import Actor
from app.policy.flags import compute_permissions
from app.schemas.auth import Me
from app.services.policy import PolicyService


class MeService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def spoke_departments(self, user_id: uuid.UUID) -> frozenset[str]:
        statement = select(SpokeAssignment.department_id).where(
            SpokeAssignment.user_id == user_id, SpokeAssignment.revoked_at.is_(None)
        )
        return frozenset(self._session.scalars(statement))

    def actor_for(self, user: User) -> Actor:
        return Actor(
            id=user.id,
            global_role=user.global_role,
            department_id=user.home_department_id,
            spoke_department_ids=self.spoke_departments(user.id),
            name=user.name,
            email=user.email,
        )

    def load_active_actor(self, user_id: uuid.UUID) -> Actor | None:
        user = self._session.get(User, user_id)
        if user is None or user.state is not AccountState.ACTIVE:
            return None
        return self.actor_for(user)

    def me(self, actor: Actor) -> Me:
        user = self._session.get(User, actor.id)
        if user is None:
            raise LookupError("actor no longer exists")
        policy = PolicyService(self._session).current()
        return Me(
            id=str(user.id),
            name=user.name,
            email=user.email,
            title=user.title,
            roles=actor.roles,
            department_id=user.home_department_id,
            spoke_departments=sorted(actor.spoke_department_ids),
            permissions=compute_permissions(actor, policy.admins_can_manage_departments),
            mfa_enabled=user.mfa_enabled,
            theme=user.theme,
        )
