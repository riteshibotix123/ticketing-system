import uuid

import pytest

from app.core.enums import Role
from app.policy import Actor
from app.policy.permissions import can_decide_signup


def make_actor(role: Role = Role.EMPLOYEE, spokes: frozenset[str] = frozenset()) -> Actor:
    return Actor(
        id=uuid.uuid4(),
        global_role=role,
        department_id="IT",
        spoke_department_ids=spokes,
        name="Approver",
        email="approver@ibotix.ai",
    )


EMPLOYEE = make_actor()
SPOKE = make_actor(spokes=frozenset({"IT"}))
ADMIN = make_actor(Role.ADMIN)
SUPER_ADMIN = make_actor(Role.SUPER_ADMIN)


@pytest.mark.parametrize(
    ("actor", "requested", "expected"),
    [
        (EMPLOYEE, Role.EMPLOYEE, False),
        (EMPLOYEE, Role.ADMIN, False),
        (EMPLOYEE, Role.SUPER_ADMIN, False),
        (SPOKE, Role.EMPLOYEE, False),
        (SPOKE, Role.ADMIN, False),
        (SPOKE, Role.SUPER_ADMIN, False),
        (ADMIN, Role.EMPLOYEE, True),
        (ADMIN, Role.ADMIN, False),
        (ADMIN, Role.SUPER_ADMIN, False),
        (SUPER_ADMIN, Role.EMPLOYEE, True),
        (SUPER_ADMIN, Role.ADMIN, True),
        (SUPER_ADMIN, Role.SUPER_ADMIN, True),
    ],
)
def test_approval_chain_matrix(actor: Actor, requested: Role, expected: bool) -> None:
    assert can_decide_signup(actor, requested, None, uuid.uuid4()) is expected


@pytest.mark.parametrize("actor", [EMPLOYEE, ADMIN, SUPER_ADMIN])
@pytest.mark.parametrize("requested", [Role.EMPLOYEE, Role.ADMIN, Role.SUPER_ADMIN])
def test_nobody_decides_their_own_request(actor: Actor, requested: Role) -> None:
    assert can_decide_signup(actor, requested, None, actor.id) is False
    assert can_decide_signup(actor, requested, requested, actor.id) is False


@pytest.mark.parametrize(
    ("actor", "requested", "approved", "expected"),
    [
        (ADMIN, Role.EMPLOYEE, Role.EMPLOYEE, True),
        (ADMIN, Role.EMPLOYEE, Role.ADMIN, False),
        (ADMIN, Role.EMPLOYEE, Role.SUPER_ADMIN, False),
        (ADMIN, Role.ADMIN, Role.EMPLOYEE, False),
        (SUPER_ADMIN, Role.EMPLOYEE, Role.SUPER_ADMIN, True),
        (SUPER_ADMIN, Role.SUPER_ADMIN, Role.EMPLOYEE, True),
    ],
)
def test_authority_needed_for_higher_role(
    actor: Actor, requested: Role, approved: Role, expected: bool
) -> None:
    assert can_decide_signup(actor, requested, approved, uuid.uuid4()) is expected


def test_spoke_is_never_a_signup_role() -> None:
    assert can_decide_signup(SUPER_ADMIN, Role.EMPLOYEE, Role.SPOKE, uuid.uuid4()) is False
    assert can_decide_signup(SUPER_ADMIN, Role.SPOKE, None, uuid.uuid4()) is False
