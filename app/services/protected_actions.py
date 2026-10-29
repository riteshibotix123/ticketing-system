import uuid
from collections.abc import Iterable
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import (
    AccountState,
    ProtectedActionKind,
    ProtectedActionStatus,
    Role,
    TicketStatus,
)
from app.core.errors import (
    conflict,
    forbidden,
    not_found,
    protected_action_blocked,
    validation_error,
)
from app.core.events import (
    ProtectedActionDecided,
    ProtectedActionRequested,
    UserDeactivated,
    publish,
)
from app.core.pagination import PageParams, fetch_page
from app.models.identity import ProtectedActionRequest, RefreshToken, User
from app.models.org import Department
from app.models.ticket import Ticket
from app.policy import Actor
from app.policy.flags import SUPERADMINS_PROTECT, has_permission
from app.policy.permissions import (
    can_decide_protected_action,
    is_independent_super_admin,
    keeps_minimum_super_admins,
)
from app.schemas.common import Page
from app.schemas.users import ProtectedActionOut
from app.services.audit import AuditService
from app.services.policy import PolicyService
from app.services.spokes import SpokeService, user_ref

PROTECTED_ACTION_LIFETIME = timedelta(hours=72)
CLOSED_TICKET_STATUSES = (TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED)
TARGET_FIELD = "target_user_id"
INVALID_TARGET = "Choose another active Super Admin"
MINIMUM_SUPER_ADMINS = "At least two active Super Admins must remain"


class AccountEffects:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock
        self._audit = AuditService(session, clock)
        self._spokes = SpokeService(session, clock)

    def open_ticket_count(self, user_id: uuid.UUID) -> int:
        statement = select(func.count(Ticket.id)).where(
            (Ticket.owner_id == user_id) | (Ticket.assignee_id == user_id),
            Ticket.status.not_in(CLOSED_TICKET_STATUSES),
        )
        return self._session.scalar(statement) or 0

    def deactivate(self, user: User, actor_id: uuid.UUID, reason: str) -> int:
        now = self._clock.now()
        previous_state = user.state
        user.state = AccountState.DEACTIVATED
        user.deactivated_by_id = actor_id
        user.deactivated_at = now
        user.deactivation_reason = reason
        user.updated_at = now
        self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now, updated_at=now)
        )
        revoked = self._spokes.revoke_all(user.id, actor_id)
        departments = list(
            self._session.scalars(
                select(Department)
                .where(Department.escalation_contact_user_id == user.id)
                .order_by(Department.id)
                .with_for_update()
            )
        )
        for department in departments:
            department.escalation_contact_user_id = None
            department.updated_at = now
        self._session.flush()
        count = self.open_ticket_count(user.id)
        self._audit.record(
            action="user_deactivated",
            object_type="user",
            object_id=user.id,
            actor_id=actor_id,
            old_value={"state": previous_state, "spoke_departments": revoked},
            new_value={
                "state": AccountState.DEACTIVATED,
                "open_ticket_count": count,
                "cleared_escalation_departments": [department.id for department in departments],
            },
            reason=reason,
        )
        publish(
            self._session,
            UserDeactivated(
                actor_id=actor_id, occurred_at=now, user_id=user.id, open_ticket_count=count
            ),
        )
        return count


class ProtectedActionService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock
        self._audit = AuditService(session, clock)
        self._effects = AccountEffects(session, clock)

    def list_actions(
        self, actor: Actor, status: ProtectedActionStatus | None, params: PageParams
    ) -> Page[ProtectedActionOut]:
        self._require_protector(actor)
        statement = select(ProtectedActionRequest).order_by(
            ProtectedActionRequest.created_at.desc(), ProtectedActionRequest.id.desc()
        )
        if status is not None:
            statement = statement.where(ProtectedActionRequest.status == status)
        result = fetch_page(self._session, statement, params)
        users = self._users(self._user_ids(result.items))
        return Page[ProtectedActionOut](
            items=[self._to_out(actor, item, users) for item in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    def create(
        self, actor: Actor, kind: ProtectedActionKind, target_user_id: str, reason: str
    ) -> ProtectedActionOut:
        self._require_protector(actor)
        try:
            target_id = uuid.UUID(target_user_id)
        except ValueError as exc:
            raise validation_error({TARGET_FIELD: INVALID_TARGET}) from exc
        request = self.request(actor, kind, target_id, reason)
        return self._to_out(actor, request, self._users(self._user_ids([request])))

    def request(
        self,
        actor: Actor,
        kind: ProtectedActionKind,
        target_id: uuid.UUID,
        reason: str,
    ) -> ProtectedActionRequest:
        self._require_protector(actor)
        super_admins = self._lock_active_super_admins()
        if target_id == actor.id or target_id not in {user.id for user in super_admins}:
            raise validation_error({TARGET_FIELD: INVALID_TARGET})
        duplicate = self._session.scalars(
            select(ProtectedActionRequest.id).where(
                ProtectedActionRequest.kind == kind,
                ProtectedActionRequest.target_user_id == target_id,
                ProtectedActionRequest.status == ProtectedActionStatus.PENDING,
            )
        ).first()
        if duplicate is not None:
            raise conflict("A pending request of this kind already exists for this Super Admin")
        if not keeps_minimum_super_admins(len(super_admins)):
            raise protected_action_blocked(MINIMUM_SUPER_ADMINS)
        now = self._clock.now()
        request = ProtectedActionRequest(
            kind=kind,
            target_user_id=target_id,
            requested_by_id=actor.id,
            status=ProtectedActionStatus.PENDING,
            reason=reason,
            expires_at=now + PROTECTED_ACTION_LIFETIME,
            created_at=now,
            updated_at=now,
        )
        self._session.add(request)
        self._session.flush()
        self._audit.record(
            action="protected_action_requested",
            object_type="protected_action",
            object_id=request.id,
            actor_id=actor.id,
            new_value={"kind": kind, "target_user_id": target_id},
            reason=reason,
            is_security_limited=True,
        )
        publish(
            self._session,
            ProtectedActionRequested(
                actor_id=actor.id, occurred_at=now, protected_action_id=request.id
            ),
        )
        return request

    def approve(self, actor: Actor, action_id: str) -> ProtectedActionOut:
        request = self._load_for_decision(actor, action_id)
        super_admins = {user.id: user for user in self._lock_active_super_admins()}
        target = super_admins.get(request.target_user_id)
        if target is None:
            raise conflict("The target is no longer an active Super Admin")
        if not keeps_minimum_super_admins(len(super_admins)):
            raise protected_action_blocked(MINIMUM_SUPER_ADMINS)
        now = self._clock.now()
        if request.kind is ProtectedActionKind.DEACTIVATE_SUPER_ADMIN:
            self._effects.deactivate(target, actor.id, request.reason)
            old_value: dict[str, object] = {"state": AccountState.ACTIVE}
            new_value: dict[str, object] = {"state": AccountState.DEACTIVATED}
        else:
            target.global_role = Role.ADMIN
            target.updated_at = now
            old_value = {"role": Role.SUPER_ADMIN}
            new_value = {"role": Role.ADMIN}
        self._decide(request, actor, ProtectedActionStatus.APPROVED, None)
        self._audit.record(
            action="protected_action_approved",
            object_type="protected_action",
            object_id=request.id,
            actor_id=actor.id,
            old_value={"kind": request.kind, "target_user_id": target.id, **old_value},
            new_value=new_value,
            is_security_limited=True,
        )
        publish(
            self._session,
            ProtectedActionDecided(
                actor_id=actor.id, occurred_at=now, protected_action_id=request.id
            ),
        )
        return self._to_out(actor, request, self._users(self._user_ids([request])))

    def reject(self, actor: Actor, action_id: str, reason: str) -> ProtectedActionOut:
        request = self._load_for_decision(actor, action_id)
        now = self._clock.now()
        self._decide(request, actor, ProtectedActionStatus.REJECTED, reason)
        self._audit.record(
            action="protected_action_rejected",
            object_type="protected_action",
            object_id=request.id,
            actor_id=actor.id,
            old_value={"kind": request.kind, "target_user_id": request.target_user_id},
            reason=reason,
            is_security_limited=True,
        )
        publish(
            self._session,
            ProtectedActionDecided(
                actor_id=actor.id, occurred_at=now, protected_action_id=request.id
            ),
        )
        return self._to_out(actor, request, self._users(self._user_ids([request])))

    def _require_protector(self, actor: Actor) -> None:
        policy = PolicyService(self._session).current()
        if not has_permission(actor, SUPERADMINS_PROTECT, policy.admins_can_manage_departments):
            raise forbidden()

    def _load_for_decision(self, actor: Actor, action_id: str) -> ProtectedActionRequest:
        self._require_protector(actor)
        try:
            parsed = uuid.UUID(action_id)
        except ValueError as exc:
            raise not_found() from exc
        request = self._session.get(
            ProtectedActionRequest, parsed, with_for_update=True, populate_existing=True
        )
        if request is None:
            raise not_found()
        if not is_independent_super_admin(actor, request.requested_by_id, request.target_user_id):
            raise forbidden("A different Super Admin must decide this request")
        if request.status is not ProtectedActionStatus.PENDING:
            raise conflict("This request has already been decided")
        if request.expires_at <= self._clock.now():
            raise conflict("This request has expired")
        return request

    def _decide(
        self,
        request: ProtectedActionRequest,
        actor: Actor,
        status: ProtectedActionStatus,
        reason: str | None,
    ) -> None:
        now = self._clock.now()
        request.status = status
        request.decided_by_id = actor.id
        request.decided_at = now
        request.decision_reason = reason
        request.updated_at = now
        self._session.flush()

    def _lock_active_super_admins(self) -> list[User]:
        statement = (
            select(User)
            .where(User.global_role == Role.SUPER_ADMIN, User.state == AccountState.ACTIVE)
            .order_by(User.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return list(self._session.scalars(statement))

    def _user_ids(self, requests: Iterable[ProtectedActionRequest]) -> set[uuid.UUID]:
        ids: set[uuid.UUID] = set()
        for request in requests:
            ids.update({request.target_user_id, request.requested_by_id})
            if request.decided_by_id is not None:
                ids.add(request.decided_by_id)
        return ids

    def _users(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
        if not ids:
            return {}
        users = self._session.scalars(select(User).where(User.id.in_(ids)))
        return {user.id: user for user in users}

    def _to_out(
        self, actor: Actor, request: ProtectedActionRequest, users: dict[uuid.UUID, User]
    ) -> ProtectedActionOut:
        decider = users.get(request.decided_by_id) if request.decided_by_id else None
        return ProtectedActionOut(
            id=str(request.id),
            kind=request.kind,
            target=user_ref(users[request.target_user_id]),
            requested_by=user_ref(users[request.requested_by_id]),
            reason=request.reason,
            status=request.status,
            decided_by=user_ref(decider) if decider is not None else None,
            decision_reason=request.decision_reason,
            created_at=request.created_at,
            expires_at=request.expires_at,
            can_decide=can_decide_protected_action(
                actor,
                request.requested_by_id,
                request.target_user_id,
                request.status,
                request.expires_at,
                self._clock.now(),
            ),
        )
