import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import forbidden, validation_error
from app.core.pagination import PageParams, fetch_page
from app.models.audit import AuditLog
from app.models.identity import User
from app.policy import Actor
from app.policy.flags import AUDIT_VIEW_ALL, has_permission
from app.queries.audit import AuditFilters, audit_statement
from app.schemas.audit import AuditEntryOut
from app.schemas.common import SYSTEM_ACTOR, Page, SystemActor, UserRef
from app.services.policy import PolicyService
from app.services.spokes import user_ref


def parse_actor_id(value: str | None) -> uuid.UUID | None:
    if value is None or not value.strip():
        return None
    try:
        return uuid.UUID(value.strip())
    except ValueError as exc:
        raise validation_error({"actor_id": "Must be a valid id"}) from exc


class AuditReadService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_entries(
        self,
        actor: Actor,
        params: PageParams,
        *,
        q: str | None = None,
        actor_id: str | None = None,
        action: str | None = None,
        ticket_id: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> Page[AuditEntryOut]:
        policy = PolicyService(self._session).current()
        if not has_permission(actor, AUDIT_VIEW_ALL, policy.admins_can_manage_departments):
            raise forbidden()
        filters = AuditFilters(
            q=q,
            actor_id=parse_actor_id(actor_id),
            action=action.strip() if action and action.strip() else None,
            ticket_no=ticket_id.strip() if ticket_id and ticket_id.strip() else None,
            created_from=created_from,
            created_to=created_to,
        )
        result = fetch_page(self._session, audit_statement(actor, filters), params)
        users = self._users({entry.actor_id for entry in result.items if entry.actor_id})
        return Page[AuditEntryOut](
            items=[self._entry_out(entry, users) for entry in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    def _users(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
        if not user_ids:
            return {}
        rows = self._session.scalars(select(User).where(User.id.in_(user_ids)))
        return {user.id: user for user in rows}

    @staticmethod
    def _entry_out(entry: AuditLog, users: dict[uuid.UUID, User]) -> AuditEntryOut:
        author: UserRef | SystemActor = (
            user_ref(users[entry.actor_id])
            if entry.actor_id is not None and entry.actor_id in users
            else SYSTEM_ACTOR
        )
        return AuditEntryOut(
            id=str(entry.id),
            at=entry.created_at,
            actor=author,
            action=entry.action,
            object_type=entry.object_type,
            object_id=entry.object_id,
            old_value=entry.old_value,
            new_value=entry.new_value,
            reason=entry.reason,
            detail=entry.detail,
        )
