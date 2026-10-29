import uuid

import pytest

from app.core.enums import Role
from app.policy import Actor
from app.policy.flags import TICKET_OPERATION_FLAGS, compute_permissions, has_permission

ADMIN_BASE = {
    "tickets.create",
    "tickets.view_all",
    *TICKET_OPERATION_FLAGS,
    "users.approve_employee",
    "audit.view_all",
    "reports.view_org",
}
ADMIN_DEPARTMENT_FLAGS = {"users.manage_roles", "departments.manage"}
SUPER_ADMIN_ONLY = {
    "users.approve_admin",
    "users.approve_super_admin",
    "admins.manage",
    "superadmins.protect",
    "confidential.manage",
    "policy.manage",
}


def make_actor(
    role: Role = Role.EMPLOYEE, spoke_departments: frozenset[str] = frozenset()
) -> Actor:
    return Actor(
        id=uuid.uuid4(),
        global_role=role,
        department_id="IT",
        spoke_department_ids=spoke_departments,
        name="Test User",
        email="test@ibotix.ai",
    )


@pytest.mark.parametrize("toggle", [True, False])
def test_employee_only_creates_tickets(toggle: bool) -> None:
    assert compute_permissions(make_actor(), toggle) == ["tickets.create"]


def test_spoke_gets_department_and_ticket_operation_flags() -> None:
    permissions = set(compute_permissions(make_actor(spoke_departments=frozenset({"IT"})), True))
    assert permissions == {"tickets.create", "tickets.view_department", *TICKET_OPERATION_FLAGS}


def test_admin_with_toggle_on_manages_departments() -> None:
    permissions = set(compute_permissions(make_actor(Role.ADMIN), True))
    assert permissions == ADMIN_BASE | ADMIN_DEPARTMENT_FLAGS


def test_admin_with_toggle_off_loses_department_management() -> None:
    permissions = set(compute_permissions(make_actor(Role.ADMIN), False))
    assert permissions == ADMIN_BASE


def test_admin_who_is_also_spoke_gets_department_view() -> None:
    actor = make_actor(Role.ADMIN, frozenset({"HR"}))
    permissions = set(compute_permissions(actor, True))
    assert permissions == ADMIN_BASE | ADMIN_DEPARTMENT_FLAGS | {"tickets.view_department"}


@pytest.mark.parametrize("toggle", [True, False])
def test_super_admin_always_has_everything(toggle: bool) -> None:
    permissions = set(compute_permissions(make_actor(Role.SUPER_ADMIN), toggle))
    assert permissions == ADMIN_BASE | ADMIN_DEPARTMENT_FLAGS | SUPER_ADMIN_ONLY


def test_permissions_have_stable_order_and_no_duplicates() -> None:
    permissions = compute_permissions(make_actor(Role.SUPER_ADMIN, frozenset({"IT"})), True)
    assert len(permissions) == len(set(permissions))
    assert permissions[0] == "tickets.create"
    assert permissions[-1] == "reports.view_org"


def test_has_permission() -> None:
    admin = make_actor(Role.ADMIN)
    assert has_permission(admin, "departments.manage", True)
    assert not has_permission(admin, "departments.manage", False)
    assert not has_permission(admin, "policy.manage", True)


def test_actor_roles() -> None:
    assert make_actor().roles == [Role.EMPLOYEE]
    assert make_actor(spoke_departments=frozenset({"IT"})).roles == [Role.EMPLOYEE, Role.SPOKE]
    assert make_actor(Role.ADMIN).roles == [Role.EMPLOYEE, Role.ADMIN]
    assert make_actor(Role.SUPER_ADMIN, frozenset({"IT"})).roles == [
        Role.EMPLOYEE,
        Role.SPOKE,
        Role.SUPER_ADMIN,
    ]


def test_actor_has_role() -> None:
    spoke = make_actor(spoke_departments=frozenset({"IT"}))
    assert spoke.has_role(Role.EMPLOYEE)
    assert spoke.has_role(Role.SPOKE)
    assert not spoke.has_role(Role.ADMIN)
    assert not make_actor(Role.ADMIN).has_role(Role.SUPER_ADMIN)
