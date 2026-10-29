import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import conflict, forbidden, not_found
from app.models.org import Category, Department
from app.policy import Actor
from app.policy.permissions import can_manage_departments
from app.schemas.org import CategoryOut, SlaModeChange
from app.services.audit import AuditService
from app.services.policy import PolicyService

DUPLICATE_CATEGORY = "A category with this name already exists in the department"


def category_out(category: Category) -> CategoryOut:
    return CategoryOut(
        id=str(category.id),
        department_id=category.department_id,
        name=category.name,
        confidential=category.is_confidential,
        active=category.is_active,
        sla_mode=category.sla_mode,
    )


class CategoryService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock
        self._audit = AuditService(session, clock)

    def create(
        self, actor: Actor, department_id: str, name: str, confidential: bool
    ) -> CategoryOut:
        self._require_manager(actor)
        department = self._session.get(Department, department_id, with_for_update=True)
        if department is None:
            raise not_found()
        self._ensure_unique(department.id, name, None)
        now = self._clock.now()
        category = Category(
            department_id=department.id,
            name=name,
            is_confidential=confidential,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self._session.add(category)
        self._session.flush()
        self._audit.record(
            action="category_created",
            object_type="category",
            object_id=category.id,
            actor_id=actor.id,
            new_value={"name": name, "confidential": confidential},
            department_id=department.id,
        )
        return category_out(category)

    def update(
        self,
        actor: Actor,
        category_id: str,
        name: str | None,
        active: bool | None,
        confidential: bool | None,
        basis: SlaModeChange | None = None,
    ) -> CategoryOut:
        self._require_manager(actor)
        category = self._load(category_id)
        old: dict[str, object] = {}
        new: dict[str, object] = {}
        if name is not None and name != category.name:
            self._ensure_unique(category.department_id, name, category.id)
            old["name"], new["name"] = category.name, name
            category.name = name
        if active is not None and active != category.is_active:
            old["active"], new["active"] = category.is_active, active
            category.is_active = active
        if confidential is not None and confidential != category.is_confidential:
            old["confidential"], new["confidential"] = category.is_confidential, confidential
            category.is_confidential = confidential
        if new:
            category.updated_at = self._clock.now()
            self._session.flush()
            self._audit.record(
                action="category_updated",
                object_type="category",
                object_id=category.id,
                actor_id=actor.id,
                old_value=old,
                new_value=new,
                department_id=category.department_id,
            )
        if basis is not None and basis.sla_mode != category.sla_mode:
            previous = category.sla_mode
            category.sla_mode = basis.sla_mode
            category.updated_at = self._clock.now()
            self._session.flush()
            self._audit.record(
                action="sla_basis_changed",
                object_type="category",
                object_id=category.id,
                actor_id=actor.id,
                old_value={"sla_mode": previous},
                new_value={"sla_mode": basis.sla_mode},
                department_id=category.department_id,
            )
        return category_out(category)

    def deactivate(self, actor: Actor, category_id: str) -> None:
        self._require_manager(actor)
        category = self._load(category_id)
        if not category.is_active:
            return
        category.is_active = False
        category.updated_at = self._clock.now()
        self._session.flush()
        self._audit.record(
            action="category_deactivated",
            object_type="category",
            object_id=category.id,
            actor_id=actor.id,
            old_value={"active": True},
            new_value={"active": False},
            department_id=category.department_id,
        )

    def _require_manager(self, actor: Actor) -> None:
        policy = PolicyService(self._session).current()
        if not can_manage_departments(actor, policy.admins_can_manage_departments):
            raise forbidden()

    def _load(self, category_id: str) -> Category:
        try:
            parsed = uuid.UUID(category_id)
        except ValueError as exc:
            raise not_found() from exc
        category = self._session.get(Category, parsed, with_for_update=True)
        if category is None:
            raise not_found()
        return category

    def _ensure_unique(self, department_id: str, name: str, exclude_id: uuid.UUID | None) -> None:
        statement = select(Category.id).where(
            Category.department_id == department_id,
            func.lower(Category.name) == name.lower(),
        )
        if exclude_id is not None:
            statement = statement.where(Category.id != exclude_id)
        if self._session.scalars(statement).first() is not None:
            raise conflict(DUPLICATE_CATEGORY)
