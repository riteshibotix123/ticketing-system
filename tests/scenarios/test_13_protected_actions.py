from app.core.enums import AccountState, Role
from tests.factories import make_user
from tests.scenarios.helpers import PASSWORD_HASH, Portal, error_code


def test_two_super_admins_cannot_drop_below_the_minimum(portal: Portal) -> None:
    response = portal.post(
        "karan",
        "/protected-actions",
        {
            "kind": "deactivate_super_admin",
            "target_user_id": str(portal.org["mira"].id),
            "reason": "Leaving the company",
        },
    )
    assert response.status_code == 409
    assert error_code(response) == "protected_action_blocked"
    mira = portal.org["mira"]
    direct = portal.post("karan", f"/users/{mira.id}/deactivate", {"reason": "Leaving the company"})
    assert direct.status_code == 409
    assert error_code(direct) == "protected_action_blocked"
    portal.db.refresh(portal.org["mira"])
    assert portal.org["mira"].state is AccountState.ACTIVE


def test_second_super_admin_must_approve(portal: Portal) -> None:
    zed = make_user(
        portal.db,
        portal.org.departments["ADM"],
        email="zed@ibotix.ai",
        name="Zed Super",
        role=Role.SUPER_ADMIN,
        password_hash=PASSWORD_HASH,
    )
    portal.org.users["zed"] = zed
    portal.db.commit()

    created = portal.post(
        "karan",
        "/protected-actions",
        {"kind": "deactivate_super_admin", "target_user_id": str(zed.id), "reason": "Leaving"},
    )
    assert created.status_code == 200, created.text
    action = portal.ok(created)
    assert action["status"] == "pending"
    assert action["can_decide"] is False
    identifier = action["id"]

    assert portal.post("karan", f"/protected-actions/{identifier}/approve").status_code == 403
    assert portal.post("zed", f"/protected-actions/{identifier}/approve").status_code == 403
    assert portal.post("priya", f"/protected-actions/{identifier}/approve").status_code == 403
    approved = portal.ok(portal.post("mira", f"/protected-actions/{identifier}/approve"))
    assert approved["status"] == "approved"
    portal.db.refresh(zed)
    assert zed.state is AccountState.DEACTIVATED

    again = portal.post(
        "karan",
        "/protected-actions",
        {
            "kind": "demote_super_admin",
            "target_user_id": str(portal.org["mira"].id),
            "reason": "Restructuring",
        },
    )
    assert again.status_code == 409
    assert error_code(again) == "protected_action_blocked"


def test_admin_demotion_of_super_admin_is_refused(portal: Portal) -> None:
    response = portal.delete("karan", f"/admins/{portal.org['mira'].id}")
    assert response.status_code == 409
    assert error_code(response) == "protected_action_blocked"
