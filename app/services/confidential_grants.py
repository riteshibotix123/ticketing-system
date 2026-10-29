import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import AccountState
from app.core.errors import conflict, forbidden, not_found, validation_error
from app.core.events import ConfidentialGrantChanged, publish
from app.models.identity import User
from app.models.org import Category, ConfidentialGrant
from app.policy import Actor
from app.policy.permissions import can_manage_grants
from app.schemas.org import ConfidentialGrantOut
from app.services.audit import AuditService
from app.services.categories import category_out
from app.services.policy import PolicyService
from app.services.spokes import user_ref

USER_FIELD = "user_id"
CATEGORY_FIELD = "category_id"
INVALID_USER = "Choose an active user"
INVALID_CATEGORY = "Choose an active confidential category"
INVALID_ID = "Enter a valid id"


def _parse(value: str, field: str, message: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise validation_error({field: message}) from exc


class ConfidentialGrantService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock
        self._audit = AuditService(session, clock)

    def list_grants(
        self, actor: Actor, category_id: str | None, user_id: str | None
    ) -> list[ConfidentialGrantOut]:
        self._require_manager(actor)
        statement = (
            select(ConfidentialGrant)
            .where(ConfidentialGrant.revoked_at.is_(None))
            .order_by(ConfidentialGrant.granted_at.desc(), ConfidentialGrant.id)
        )
        if category_id is not None:
            statement = statement.where(
                ConfidentialGrant.category_id == _parse(category_id, CATEGORY_FIELD, INVALID_ID)
            )
        if user_id is not None:
            statement = statement.where(
                ConfidentialGrant.user_id == _parse(user_id, USER_FIELD, INVALID_ID)
            )
        return self._to_out(list(self._session.scalars(statement)))

    def create(self, actor: Actor, user_id: str, category_id: str) -> ConfidentialGrantOut:
        self._require_manager(actor)
        user = self._session.get(User, _parse(user_id, USER_FIELD, INVALID_USER))
        if user is None or user.state is not AccountState.ACTIVE:
            raise validation_error({USER_FIELD: INVALID_USER})
        category = self._session.get(
            Category, _parse(category_id, CATEGORY_FIELD, INVALID_CATEGORY), with_for_update=True
        )
        if category is None or not category.is_active or not category.is_confidential:
            raise validation_error({CATEGORY_FIELD: INVALID_CATEGORY})
        duplicate = self._session.scalars(
            select(ConfidentialGrant.id).where(
                ConfidentialGrant.user_id == user.id,
                ConfidentialGrant.category_id == category.id,
                ConfidentialGrant.revoked_at.is_(None),
            )
        ).first()
        if duplicate is not None:
            raise conflict("This user already holds a grant for the category")
        now = self._clock.now()
        grant = ConfidentialGrant(
            user_id=user.id, category_id=category.id, granted_by_id=actor.id, granted_at=now
        )
        self._session.add(grant)
        self._session.flush()
        self._audit.record(
            action="confidential_grant_added",
            object_type="confidential_grant",
            object_id=grant.id,
            actor_id=actor.id,
            new_value={"user_id": user.id, "category_id": category.id},
            department_id=category.department_id,
            is_security_limited=True,
        )
        publish(
            self._session,
            ConfidentialGrantChanged(
                actor_id=actor.id, occurred_at=now, user_id=user.id, category_id=category.id
            ),
        )
        return self._to_out([grant])[0]

    def revoke(self, actor: Actor, grant_id: str) -> None:
        self._require_manager(actor)
        try:
            parsed = uuid.UUID(grant_id)
        except ValueError as exc:
            raise not_found() from exc
        grant = self._session.get(ConfidentialGrant, parsed, with_for_update=True)
        if grant is None or grant.revoked_at is not None:
            raise not_found()
        now = self._clock.now()
        grant.revoked_at = now
        grant.revoked_by_id = actor.id
        self._session.flush()
        category = self._session.get(Category, grant.category_id)
        self._audit.record(
            action="confidential_grant_revoked",
            object_type="confidential_grant",
            object_id=grant.id,
            actor_id=actor.id,
            old_value={"user_id": grant.user_id, "category_id": grant.category_id},
            department_id=category.department_id if category is not None else None,
            is_security_limited=True,
        )
        publish(
            self._session,
            ConfidentialGrantChanged(
                actor_id=actor.id,
                occurred_at=now,
                user_id=grant.user_id,
                category_id=grant.category_id,
            ),
        )

    def _require_manager(self, actor: Actor) -> None:
        policy = PolicyService(self._session).current()
        if not can_manage_grants(actor, policy.admins_can_manage_departments):
            raise forbidden()

    def _to_out(self, grants: Sequence[ConfidentialGrant]) -> list[ConfidentialGrantOut]:
        user_ids = {grant.user_id for grant in grants} | {
            grant.granted_by_id for grant in grants if grant.granted_by_id is not None
        }
        category_ids = {grant.category_id for grant in grants}
        users = self._users(user_ids)
        categories = (
            {
                category.id: category
                for category in self._session.scalars(
                    select(Category).where(Category.id.in_(category_ids))
                )
            }
            if category_ids
            else {}
        )
        result: list[ConfidentialGrantOut] = []
        for grant in grants:
            granter = users.get(grant.granted_by_id) if grant.granted_by_id else None
            result.append(
                ConfidentialGrantOut(
                    id=str(grant.id),
                    user=user_ref(users[grant.user_id]),
                    category=category_out(categories[grant.category_id]),
                    granted_by=user_ref(granter) if granter is not None else None,
                    granted_at=grant.granted_at,
                )
            )
        return result

    def _users(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
        if not ids:
            return {}
        users = self._session.scalars(select(User).where(User.id.in_(ids)))
        return {user.id: user for user in users}
