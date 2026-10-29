import uuid
from collections.abc import Iterable

from sqlalchemy import ColumnElement, exists, or_, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import AccountState
from app.models.identity import User
from app.models.org import SpokeAssignment
from app.schemas.common import UserRef
from app.services.audit import AuditService


def user_ref(user: User) -> UserRef:
    return UserRef(id=str(user.id), name=user.name, email=user.email, title=user.title)


def active_spoke_of(department_id: str) -> ColumnElement[bool]:
    return exists().where(
        SpokeAssignment.user_id == User.id,
        SpokeAssignment.department_id == department_id,
        SpokeAssignment.revoked_at.is_(None),
    )


def any_active_spoke() -> ColumnElement[bool]:
    return exists().where(
        SpokeAssignment.user_id == User.id,
        SpokeAssignment.revoked_at.is_(None),
    )


def department_member(department_id: str) -> ColumnElement[bool]:
    return or_(User.home_department_id == department_id, active_spoke_of(department_id))


class SpokeService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock
        self._audit = AuditService(session, clock)

    def active_departments(self, user_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        wanted = set(user_ids)
        mapped: dict[uuid.UUID, list[str]] = {user_id: [] for user_id in wanted}
        if not wanted:
            return mapped
        rows = self._session.execute(
            select(SpokeAssignment.user_id, SpokeAssignment.department_id)
            .where(SpokeAssignment.user_id.in_(wanted), SpokeAssignment.revoked_at.is_(None))
            .order_by(SpokeAssignment.department_id)
        )
        for user_id, department_id in rows:
            mapped[user_id].append(department_id)
        return mapped

    def members(self, department_id: str) -> list[User]:
        statement = (
            select(User)
            .where(User.state == AccountState.ACTIVE, department_member(department_id))
            .order_by(User.name, User.id)
        )
        return list(self._session.scalars(statement))

    def replace(
        self,
        user: User,
        department_ids: Iterable[str],
        actor_id: uuid.UUID,
        reason: str,
    ) -> tuple[list[str], list[str]]:
        wanted = set(department_ids)
        current = self._lock_active(user.id)
        held = {assignment.department_id for assignment in current}
        now = self._clock.now()
        revoked: list[str] = []
        for assignment in sorted(current, key=lambda item: item.department_id):
            if assignment.department_id in wanted:
                continue
            assignment.revoked_at = now
            assignment.revoked_by_id = actor_id
            revoked.append(assignment.department_id)
        added = sorted(wanted - held)
        for department_id in added:
            self._session.add(
                SpokeAssignment(
                    user_id=user.id,
                    department_id=department_id,
                    granted_by_id=actor_id,
                    granted_at=now,
                )
            )
        self._session.flush()
        for department_id in added:
            self._record("spoke_mapping_added", user, department_id, actor_id, reason)
        for department_id in revoked:
            self._record("spoke_mapping_revoked", user, department_id, actor_id, reason)
        return added, revoked

    def revoke_all(self, user_id: uuid.UUID, actor_id: uuid.UUID) -> list[str]:
        now = self._clock.now()
        revoked: list[str] = []
        for assignment in self._lock_active(user_id):
            assignment.revoked_at = now
            assignment.revoked_by_id = actor_id
            revoked.append(assignment.department_id)
        self._session.flush()
        return sorted(revoked)

    def _lock_active(self, user_id: uuid.UUID) -> list[SpokeAssignment]:
        statement = (
            select(SpokeAssignment)
            .where(SpokeAssignment.user_id == user_id, SpokeAssignment.revoked_at.is_(None))
            .order_by(SpokeAssignment.department_id)
            .with_for_update()
        )
        return list(self._session.scalars(statement))

    def _record(
        self, action: str, user: User, department_id: str, actor_id: uuid.UUID, reason: str
    ) -> None:
        self._audit.record(
            action=action,
            object_type="user",
            object_id=user.id,
            actor_id=actor_id,
            new_value={"department_id": department_id},
            reason=reason,
            department_id=department_id,
        )
