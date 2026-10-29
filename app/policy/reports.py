import uuid
from dataclasses import dataclass
from typing import Literal

from app.policy import Actor
from app.policy.flags import (
    REPORTS_VIEW_ORG,
    TICKETS_VIEW_ALL,
    TICKETS_VIEW_DEPARTMENT,
    has_permission,
)


@dataclass(frozen=True, slots=True)
class ReportScope:
    department_ids: frozenset[str] | None


def can_view_org_reports(actor: Actor, admins_can_manage_departments: bool) -> bool:
    return has_permission(actor, REPORTS_VIEW_ORG, admins_can_manage_departments)


def can_view_reports(actor: Actor, admins_can_manage_departments: bool) -> bool:
    return can_view_org_reports(actor, admins_can_manage_departments) or has_permission(
        actor, TICKETS_VIEW_DEPARTMENT, admins_can_manage_departments
    )


def report_scope(
    actor: Actor, admins_can_manage_departments: bool, department_id: str | None
) -> ReportScope | None:
    requested = frozenset({department_id}) if department_id is not None else None
    if can_view_org_reports(actor, admins_can_manage_departments):
        return ReportScope(requested)
    if not can_view_reports(actor, admins_can_manage_departments):
        return None
    if requested is None:
        return ReportScope(actor.spoke_department_ids)
    if requested <= actor.spoke_department_ids:
        return ReportScope(requested)
    return None


def built_in_view_scope(
    actor: Actor, admins_can_manage_departments: bool
) -> Literal["queue", "all", "mine"]:
    if actor.is_spoke:
        return "queue"
    if has_permission(actor, TICKETS_VIEW_ALL, admins_can_manage_departments):
        return "all"
    return "mine"


def sees_department_views(actor: Actor) -> bool:
    return actor.is_spoke


def owns_saved_view(actor: Actor, owner_id: uuid.UUID) -> bool:
    return actor.id == owner_id
