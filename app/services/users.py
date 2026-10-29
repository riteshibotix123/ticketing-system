import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import AccountState, ProtectedActionKind, Role
from app.core.errors import (
    conflict,
    forbidden,
    not_found,
    protected_action_blocked,
    validation_error,
)
from app.core.pagination import PageParams, fetch_page
from app.models.identity import User
from app.models.org import Department
from app.policy import Actor
from app.policy.permissions import (
    can_change_account_state,
    can_list_users,
    can_manage_account,
    can_manage_admins,
    deactivation_is_protected,
)
from app.schemas.common import Page, UserRef
from app.schemas.users import DeactivationResult, UserListItem
from app.services.audit import AuditService
from app.services.policy import PolicyService
from app.services.protected_actions import AccountEffects, ProtectedActionService
from app.services.spokes import (
    SpokeService,
    any_active_spoke,
    department_member,
    user_ref,
)

LOOKUP_MIN_LENGTH = 2
LOOKUP_LIMIT = 20
STAFF_ROLES = (Role.ADMIN, Role.SUPER_ADMIN)
USER_ID_FIELD = "user_id"
INVALID_PROMOTION_TARGET = "Choose an existing user"


class UserService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock
        self._audit = AuditService(session, clock)
        self._spokes = SpokeService(session, clock)
        self._effects = AccountEffects(session, clock)

    def list_users(
        self,
        actor: Actor,
        q: str | None,
        role: Role | None,
        state: AccountState | None,
        department_id: str | None,
        params: PageParams,
    ) -> Page[UserListItem]:
        if not can_list_users(actor, self._admins_manage_departments()):
            raise forbidden()
        statement = (
            select(User)
            .where(User.state != AccountState.PENDING_VERIFICATION)
            .order_by(User.name, User.id)
        )
        term = q.strip().lower() if q else ""
        if term:
            statement = statement.where(self._matches(term))
        if role is Role.SPOKE:
            statement = statement.where(any_active_spoke())
        elif role is not None:
            statement = statement.where(User.global_role == role)
        if state is not None:
            statement = statement.where(User.state == state)
        if department_id:
            statement = statement.where(department_member(department_id.strip()))
        result = fetch_page(self._session, statement, params)
        return Page[UserListItem](
            items=self.list_items(result.items),
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    def lookup(self, q: str) -> list[UserRef]:
        term = q.strip().lower()
        if len(term) < LOOKUP_MIN_LENGTH:
            raise validation_error({"q": f"Enter at least {LOOKUP_MIN_LENGTH} characters"})
        statement = (
            select(User)
            .where(User.state == AccountState.ACTIVE, self._matches(term))
            .order_by(User.name, User.id)
            .limit(LOOKUP_LIMIT)
        )
        return [user_ref(user) for user in self._session.scalars(statement)]

    def department_members(self, department_id: str) -> list[UserRef]:
        if self._session.get(Department, department_id) is None:
            raise not_found()
        return [user_ref(user) for user in self._spokes.members(department_id)]

    def update_roles(
        self, actor: Actor, user_id: str, spoke_departments: Sequence[str], reason: str
    ) -> UserListItem:
        user = self._load(user_id)
        if not can_manage_account(actor, user.global_role, self._admins_manage_departments()):
            raise forbidden()
        wanted = set(spoke_departments)
        known = set(self._session.scalars(select(Department.id).where(Department.id.in_(wanted))))
        unknown = sorted(wanted - known)
        if unknown:
            raise validation_error(
                {"spoke_departments": f"Unknown department: {', '.join(unknown)}"}
            )
        self._lock(user)
        if user.state is not AccountState.ACTIVE:
            raise conflict("Only an active account can be changed")
        added, revoked = self._spokes.replace(user, wanted, actor.id, reason)
        if added or revoked:
            user.updated_at = self._clock.now()
            self._session.flush()
        return self.list_item(user)

    def deactivate(self, actor: Actor, user_id: str, reason: str) -> DeactivationResult:
        user = self._load(user_id)
        self._require_state_authority(actor, user)
        if user.state is not AccountState.ACTIVE:
            raise conflict("Only an active account can be deactivated")
        if deactivation_is_protected(user.global_role):
            request = ProtectedActionService(self._session, self._clock).request(
                actor, ProtectedActionKind.DEACTIVATE_SUPER_ADMIN, user.id, reason
            )
            return DeactivationResult(
                result="protected_request_created",
                open_ticket_count=self._effects.open_ticket_count(user.id),
                protected_action_id=str(request.id),
            )
        self._lock(user)
        self._require_state_authority(actor, user)
        if user.state is not AccountState.ACTIVE or deactivation_is_protected(user.global_role):
            raise conflict("This account changed, try again")
        count = self._effects.deactivate(user, actor.id, reason)
        return DeactivationResult(
            result="deactivated", open_ticket_count=count, protected_action_id=None
        )

    def activate(self, actor: Actor, user_id: str) -> UserListItem:
        user = self._load(user_id)
        self._require_state_authority(actor, user)
        self._lock(user)
        if user.state is not AccountState.DEACTIVATED or user.approved_at is None:
            raise conflict("Only a deactivated, previously approved account can be activated")
        now = self._clock.now()
        previous_reason = user.deactivation_reason
        user.state = AccountState.ACTIVE
        user.deactivated_by_id = None
        user.deactivated_at = None
        user.deactivation_reason = None
        user.updated_at = now
        self._session.flush()
        self._audit.record(
            action="user_activated",
            object_type="user",
            object_id=user.id,
            actor_id=actor.id,
            old_value={"state": AccountState.DEACTIVATED, "reason": previous_reason},
            new_value={"state": AccountState.ACTIVE},
        )
        return self.list_item(user)

    def list_admins(self, actor: Actor) -> list[UserListItem]:
        self._require_admin_manager(actor)
        statement = (
            select(User).where(User.global_role.in_(STAFF_ROLES)).order_by(User.name, User.id)
        )
        return self.list_items(list(self._session.scalars(statement)))

    def promote_admin(self, actor: Actor, user_id: str) -> UserListItem:
        self._require_admin_manager(actor)
        try:
            parsed = uuid.UUID(user_id)
        except ValueError as exc:
            raise validation_error({USER_ID_FIELD: INVALID_PROMOTION_TARGET}) from exc
        user = self._session.get(User, parsed, with_for_update=True, populate_existing=True)
        if user is None:
            raise validation_error({USER_ID_FIELD: INVALID_PROMOTION_TARGET})
        if user.state is not AccountState.ACTIVE or user.global_role is not Role.EMPLOYEE:
            raise conflict("Only an active employee can be promoted to Admin")
        self._set_role(actor, user, Role.ADMIN, "admin_promoted")
        return self.list_item(user)

    def demote_admin(self, actor: Actor, user_id: str) -> UserListItem:
        self._require_admin_manager(actor)
        user = self._load(user_id)
        self._lock(user)
        if user.global_role is Role.SUPER_ADMIN:
            raise protected_action_blocked(
                "Demoting a Super Admin needs a protected action approved by another Super Admin"
            )
        if user.global_role is not Role.ADMIN:
            raise conflict("This account is not an Admin")
        self._set_role(actor, user, Role.EMPLOYEE, "admin_demoted")
        return self.list_item(user)

    def list_item(self, user: User) -> UserListItem:
        return self.list_items([user])[0]

    def list_items(self, users: Sequence[User]) -> list[UserListItem]:
        spokes = self._spokes.active_departments(user.id for user in users)
        return [self._to_item(user, spokes[user.id]) for user in users]

    def _to_item(self, user: User, spoke_departments: list[str]) -> UserListItem:
        roles = Actor(
            id=user.id,
            global_role=user.global_role,
            department_id=user.home_department_id,
            spoke_department_ids=frozenset(spoke_departments),
            name=user.name,
            email=user.email,
        ).roles
        return UserListItem(
            id=str(user.id),
            name=user.name,
            email=user.email,
            title=user.title,
            roles=roles,
            state=user.state,
            department_id=user.home_department_id,
            spoke_departments=spoke_departments,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
        )

    def _set_role(self, actor: Actor, user: User, role: Role, action: str) -> None:
        previous = user.global_role
        user.global_role = role
        user.updated_at = self._clock.now()
        self._session.flush()
        self._audit.record(
            action=action,
            object_type="user",
            object_id=user.id,
            actor_id=actor.id,
            old_value={"role": previous},
            new_value={"role": role},
            is_security_limited=True,
        )

    def _matches(self, term: str) -> ColumnElement[bool]:
        return or_(
            User.name.ilike(f"%{self._escape(term)}%", escape="\\"),
            User.email.ilike(f"%{self._escape(term)}%", escape="\\"),
        )

    def _escape(self, term: str) -> str:
        return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def _admins_manage_departments(self) -> bool:
        return PolicyService(self._session).current().admins_can_manage_departments

    def _require_state_authority(self, actor: Actor, user: User) -> None:
        if not can_change_account_state(
            actor, user.id, user.global_role, self._admins_manage_departments()
        ):
            raise forbidden()

    def _require_admin_manager(self, actor: Actor) -> None:
        if not can_manage_admins(actor, self._admins_manage_departments()):
            raise forbidden()

    def _load(self, user_id: str) -> User:
        try:
            parsed = uuid.UUID(user_id)
        except ValueError as exc:
            raise not_found() from exc
        user = self._session.get(User, parsed)
        if user is None or user.state is AccountState.PENDING_VERIFICATION:
            raise not_found()
        return user

    def _lock(self, user: User) -> None:
        self._session.refresh(user, with_for_update=True)
