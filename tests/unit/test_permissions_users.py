import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.enums import ProtectedActionStatus, Role
from app.policy import Actor
from app.policy.permissions import (
    can_change_account_state,
    can_decide_protected_action,
    can_list_users,
    can_manage_account,
    can_manage_admins,
    deactivation_is_protected,
    keeps_minimum_super_admins,
)

NOW = datetime(2026, 10, 27, 4, 30, tzinfo=UTC)


def make_actor(role: Role = Role.EMPLOYEE, spokes: frozenset[str] = frozenset()) -> Actor:
    return Actor(
        id=uuid.uuid4(),
        global_role=role,
        department_id="IT",
        spoke_department_ids=spokes,
        name="Actor",
        email="actor@ibotix.ai",
    )


EMPLOYEE = make_actor()
SPOKE = make_actor(spokes=frozenset({"IT"}))
ADMIN = make_actor(Role.ADMIN)
SUPER_ADMIN = make_actor(Role.SUPER_ADMIN)


@pytest.mark.parametrize(
    ("actor", "toggle", "expected"),
    [
        (EMPLOYEE, True, False),
        (SPOKE, True, False),
        (ADMIN, True, True),
        (ADMIN, False, False),
        (SUPER_ADMIN, True, True),
        (SUPER_ADMIN, False, True),
    ],
)
def test_can_list_users(actor: Actor, toggle: bool, expected: bool) -> None:
    assert can_list_users(actor, toggle) is expected


@pytest.mark.parametrize(
    ("actor", "target", "toggle", "expected"),
    [
        (EMPLOYEE, Role.EMPLOYEE, True, False),
        (SPOKE, Role.EMPLOYEE, True, False),
        (ADMIN, Role.EMPLOYEE, True, True),
        (ADMIN, Role.EMPLOYEE, False, False),
        (ADMIN, Role.ADMIN, True, False),
        (ADMIN, Role.SUPER_ADMIN, True, False),
        (SUPER_ADMIN, Role.EMPLOYEE, False, True),
        (SUPER_ADMIN, Role.ADMIN, True, True),
        (SUPER_ADMIN, Role.SUPER_ADMIN, True, True),
    ],
)
def test_can_manage_account(actor: Actor, target: Role, toggle: bool, expected: bool) -> None:
    assert can_manage_account(actor, target, toggle) is expected
    assert can_change_account_state(actor, uuid.uuid4(), target, toggle) is expected


@pytest.mark.parametrize("actor", [ADMIN, SUPER_ADMIN])
def test_never_change_own_state(actor: Actor) -> None:
    assert can_change_account_state(actor, actor.id, Role.EMPLOYEE, True) is False


def test_only_super_admin_manages_admins() -> None:
    assert can_manage_admins(SUPER_ADMIN, False) is True
    assert can_manage_admins(ADMIN, True) is False
    assert can_manage_admins(SPOKE, True) is False


def test_protected_deactivation_only_for_super_admin() -> None:
    assert deactivation_is_protected(Role.SUPER_ADMIN) is True
    assert deactivation_is_protected(Role.ADMIN) is False
    assert deactivation_is_protected(Role.EMPLOYEE) is False


@pytest.mark.parametrize(("count", "expected"), [(1, False), (2, False), (3, True), (5, True)])
def test_minimum_two_super_admins(count: int, expected: bool) -> None:
    assert keeps_minimum_super_admins(count) is expected


def test_can_decide_protected_action() -> None:
    requester = uuid.uuid4()
    target = uuid.uuid4()
    later = NOW + timedelta(hours=1)
    pending = ProtectedActionStatus.PENDING
    assert can_decide_protected_action(SUPER_ADMIN, requester, target, pending, later, NOW)
    assert not can_decide_protected_action(ADMIN, requester, target, pending, later, NOW)
    assert not can_decide_protected_action(SUPER_ADMIN, SUPER_ADMIN.id, target, pending, later, NOW)
    assert not can_decide_protected_action(
        SUPER_ADMIN, requester, SUPER_ADMIN.id, pending, later, NOW
    )
    assert not can_decide_protected_action(SUPER_ADMIN, requester, target, pending, NOW, NOW)
    assert not can_decide_protected_action(
        SUPER_ADMIN, requester, target, ProtectedActionStatus.APPROVED, later, NOW
    )
