import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import AccountState
from app.core.errors import conflict, forbidden, not_found, validation_error
from app.models.identity import User
from app.models.org import Category, Department, SpokeAssignment
from app.policy import Actor
from app.policy.permissions import can_manage_departments
from app.schemas.common import UserRef
from app.schemas.org import CategoryOut, DepartmentOut, SlaModeChange
from app.services.audit import AuditService
from app.services.categories import category_out
from app.services.policy import PolicyService
from app.services.spokes import department_member, user_ref

USER_FIELD = "user_id"
CONTACT_FIELD = "contact_id"
INVALID_SPOKE = "Choose an active user"
INVALID_CONTACT = "Choose an active member of this department"


class DepartmentService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock
        self._audit = AuditService(session, clock)

    def list_departments(self, actor: Actor) -> list[DepartmentOut]:
        statement = select(Department).order_by(Department.name, Department.id)
        if not self._manages(actor):
            statement = statement.where(Department.is_active.is_(True))
        return self.to_out(list(self._session.scalars(statement)))

    def create(self, actor: Actor, department_id: str, name: str) -> DepartmentOut:
        self._require_manager(actor)
        if self._session.get(Department, department_id) is not None:
            raise conflict("A department with this code already exists")
        now = self._clock.now()
        department = Department(
            id=department_id, name=name, is_active=False, created_at=now, updated_at=now
        )
        self._session.add(department)
        self._session.flush()
        self._audit.record(
            action="department_created",
            object_type="department",
            object_id=department.id,
            actor_id=actor.id,
            new_value={"id": department.id, "name": name, "active": False},
            department_id=department.id,
        )
        return self.one(department)

    def update(
        self,
        actor: Actor,
        department_id: str,
        name: str | None,
        active: bool | None,
        basis: SlaModeChange | None = None,
    ) -> DepartmentOut:
        self._require_manager(actor)
        department = self._load(department_id)
        old: dict[str, object] = {}
        new: dict[str, object] = {}
        if name is not None and name != department.name:
            old["name"], new["name"] = department.name, name
            department.name = name
        if active is not None and active != department.is_active:
            if active and not self._spoke_users([department.id])[department.id]:
                raise conflict("A department needs at least one active Spoke to be activated")
            old["active"], new["active"] = department.is_active, active
            department.is_active = active
        if new:
            department.updated_at = self._clock.now()
            self._session.flush()
            self._audit.record(
                action="department_updated",
                object_type="department",
                object_id=department.id,
                actor_id=actor.id,
                old_value=old,
                new_value=new,
                department_id=department.id,
            )
        if basis is not None and basis.sla_mode != department.sla_mode:
            previous = department.sla_mode
            department.sla_mode = basis.sla_mode
            department.updated_at = self._clock.now()
            self._session.flush()
            self._audit.record(
                action="sla_basis_changed",
                object_type="department",
                object_id=department.id,
                actor_id=actor.id,
                old_value={"sla_mode": previous},
                new_value={"sla_mode": basis.sla_mode},
                department_id=department.id,
            )
        return self.one(department)

    def add_spoke(self, actor: Actor, department_id: str, user_id: str) -> DepartmentOut:
        self._require_manager(actor)
        department = self._load(department_id)
        user = self._active_user(user_id, USER_FIELD, INVALID_SPOKE)
        existing = self._session.scalars(
            select(SpokeAssignment.id).where(
                SpokeAssignment.user_id == user.id,
                SpokeAssignment.department_id == department.id,
                SpokeAssignment.revoked_at.is_(None),
            )
        ).first()
        if existing is not None:
            raise conflict("This user is already a Spoke of the department")
        self._session.add(
            SpokeAssignment(
                user_id=user.id,
                department_id=department.id,
                granted_by_id=actor.id,
                granted_at=self._clock.now(),
            )
        )
        self._session.flush()
        self._audit.record(
            action="spoke_mapping_added",
            object_type="user",
            object_id=user.id,
            actor_id=actor.id,
            new_value={"department_id": department.id},
            department_id=department.id,
        )
        return self.one(department)

    def remove_spoke(self, actor: Actor, department_id: str, user_id: str) -> DepartmentOut:
        self._require_manager(actor)
        department = self._load(department_id)
        try:
            parsed = uuid.UUID(user_id)
        except ValueError as exc:
            raise not_found() from exc
        assignment = self._session.scalars(
            select(SpokeAssignment)
            .where(
                SpokeAssignment.user_id == parsed,
                SpokeAssignment.department_id == department.id,
                SpokeAssignment.revoked_at.is_(None),
            )
            .with_for_update()
        ).first()
        if assignment is None:
            raise not_found()
        assignment.revoked_at = self._clock.now()
        assignment.revoked_by_id = actor.id
        self._session.flush()
        self._audit.record(
            action="spoke_mapping_revoked",
            object_type="user",
            object_id=parsed,
            actor_id=actor.id,
            new_value={"department_id": department.id},
            department_id=department.id,
        )
        return self.one(department)

    def set_escalation_contact(
        self, actor: Actor, department_id: str, contact_id: str | None
    ) -> DepartmentOut:
        self._require_manager(actor)
        department = self._load(department_id)
        new_contact: uuid.UUID | None = None
        if contact_id is not None:
            contact = self._active_user(contact_id, CONTACT_FIELD, INVALID_CONTACT)
            member = self._session.scalars(
                select(User.id).where(User.id == contact.id, department_member(department.id))
            ).first()
            if member is None:
                raise validation_error({CONTACT_FIELD: INVALID_CONTACT})
            new_contact = contact.id
        previous = department.escalation_contact_user_id
        if previous != new_contact:
            department.escalation_contact_user_id = new_contact
            department.updated_at = self._clock.now()
            self._session.flush()
            self._audit.record(
                action="escalation_contact_changed",
                object_type="department",
                object_id=department.id,
                actor_id=actor.id,
                old_value={"contact_id": previous},
                new_value={"contact_id": new_contact},
                department_id=department.id,
            )
        return self.one(department)

    def one(self, department: Department) -> DepartmentOut:
        return self.to_out([department])[0]

    def to_out(self, departments: Sequence[Department]) -> list[DepartmentOut]:
        ids = [department.id for department in departments]
        spokes = self._spoke_users(ids)
        categories = self._categories(ids)
        contact_ids = {
            department.escalation_contact_user_id
            for department in departments
            if department.escalation_contact_user_id is not None
        }
        contacts = self._users(contact_ids)
        result: list[DepartmentOut] = []
        for department in departments:
            contact = (
                contacts.get(department.escalation_contact_user_id)
                if department.escalation_contact_user_id is not None
                else None
            )
            department_spokes = spokes[department.id]
            result.append(
                DepartmentOut(
                    id=department.id,
                    name=department.name,
                    active=department.is_active,
                    accepts_tickets=department.is_active and bool(department_spokes),
                    spokes=department_spokes,
                    escalation_contact=user_ref(contact) if contact is not None else None,
                    categories=categories[department.id],
                    sla_mode=department.sla_mode,
                )
            )
        return result

    def _spoke_users(self, department_ids: Sequence[str]) -> dict[str, list[UserRef]]:
        mapped: dict[str, list[UserRef]] = {department_id: [] for department_id in department_ids}
        if not department_ids:
            return mapped
        rows = self._session.execute(
            select(SpokeAssignment.department_id, User)
            .join(User, User.id == SpokeAssignment.user_id)
            .where(
                SpokeAssignment.department_id.in_(department_ids),
                SpokeAssignment.revoked_at.is_(None),
                User.state == AccountState.ACTIVE,
            )
            .order_by(User.name, User.id)
        )
        for department_id, user in rows:
            mapped[department_id].append(user_ref(user))
        return mapped

    def _categories(self, department_ids: Sequence[str]) -> dict[str, list[CategoryOut]]:
        mapped: dict[str, list[CategoryOut]] = {
            department_id: [] for department_id in department_ids
        }
        if not department_ids:
            return mapped
        statement = (
            select(Category)
            .where(Category.department_id.in_(department_ids))
            .order_by(Category.name, Category.id)
        )
        for category in self._session.scalars(statement):
            mapped[category.department_id].append(category_out(category))
        return mapped

    def _manages(self, actor: Actor) -> bool:
        policy = PolicyService(self._session).current()
        return can_manage_departments(actor, policy.admins_can_manage_departments)

    def _require_manager(self, actor: Actor) -> None:
        if not self._manages(actor):
            raise forbidden()

    def _load(self, department_id: str) -> Department:
        department = self._session.get(Department, department_id, with_for_update=True)
        if department is None:
            raise not_found()
        return department

    def _active_user(self, user_id: str, field: str, message: str) -> User:
        try:
            parsed = uuid.UUID(user_id)
        except ValueError as exc:
            raise validation_error({field: message}) from exc
        user = self._session.get(User, parsed)
        if user is None or user.state is not AccountState.ACTIVE:
            raise validation_error({field: message})
        return user

    def _users(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
        if not ids:
            return {}
        users = self._session.scalars(select(User).where(User.id.in_(ids)))
        return {user.id: user for user in users}
