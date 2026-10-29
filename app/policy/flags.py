from typing import Final

from app.policy import Actor

TICKETS_CREATE: Final = "tickets.create"
TICKETS_VIEW_ALL: Final = "tickets.view_all"
TICKETS_VIEW_DEPARTMENT: Final = "tickets.view_department"
TICKET_OPERATION_FLAGS: Final = (
    "tickets.acknowledge",
    "tickets.assign",
    "tickets.transfer",
    "tickets.change_priority",
    "tickets.revise_eta",
    "tickets.hold",
    "tickets.resolve",
    "tickets.close_admin",
    "tickets.reopen",
    "tickets.internal_notes",
)
USERS_APPROVE_EMPLOYEE: Final = "users.approve_employee"
USERS_APPROVE_ADMIN: Final = "users.approve_admin"
USERS_APPROVE_SUPER_ADMIN: Final = "users.approve_super_admin"
USERS_MANAGE_ROLES: Final = "users.manage_roles"
ADMINS_MANAGE: Final = "admins.manage"
SUPERADMINS_PROTECT: Final = "superadmins.protect"
CONFIDENTIAL_MANAGE: Final = "confidential.manage"
DEPARTMENTS_MANAGE: Final = "departments.manage"
POLICY_MANAGE: Final = "policy.manage"
AUDIT_VIEW_ALL: Final = "audit.view_all"
REPORTS_VIEW_ORG: Final = "reports.view_org"


def compute_permissions(actor: Actor, admins_can_manage_departments: bool) -> list[str]:
    staff = actor.is_admin_or_super_admin
    super_admin = actor.is_super_admin
    manages_departments = super_admin or (staff and admins_can_manage_departments)
    granted: list[tuple[str, bool]] = [
        (TICKETS_CREATE, True),
        (TICKETS_VIEW_ALL, staff),
        (TICKETS_VIEW_DEPARTMENT, actor.is_spoke),
        *((flag, staff or actor.is_spoke) for flag in TICKET_OPERATION_FLAGS),
        (USERS_APPROVE_EMPLOYEE, staff),
        (USERS_APPROVE_ADMIN, super_admin),
        (USERS_APPROVE_SUPER_ADMIN, super_admin),
        (USERS_MANAGE_ROLES, manages_departments),
        (ADMINS_MANAGE, super_admin),
        (SUPERADMINS_PROTECT, super_admin),
        (CONFIDENTIAL_MANAGE, super_admin),
        (DEPARTMENTS_MANAGE, manages_departments),
        (POLICY_MANAGE, super_admin),
        (AUDIT_VIEW_ALL, staff),
        (REPORTS_VIEW_ORG, staff),
    ]
    return [flag for flag, allowed in granted if allowed]


def has_permission(actor: Actor, flag: str, admins_can_manage_departments: bool) -> bool:
    return flag in compute_permissions(actor, admins_can_manage_departments)
