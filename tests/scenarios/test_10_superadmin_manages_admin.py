from sqlalchemy import select

from app.models import EmailOutbox, SignupRequest, User
from tests.scenarios.helpers import PASSWORD, Portal, error_code, field

APPLICANT = "anil.admin@ibotix.ai"


def sign_up_and_verify(portal: Portal, email: str, role: str, department: str = "ADM") -> None:
    body = {
        "name": "Anil Applicant",
        "email": email,
        "password": PASSWORD,
        "requested_role": role,
        "requested_department": department,
    }
    assert portal.anonymous("/auth/signup", body).status_code == 202
    outbox = portal.db.scalars(
        select(EmailOutbox).where(
            EmailOutbox.to_address == email, EmailOutbox.template == "verify_email"
        )
    ).one()
    verified = portal.anonymous("/auth/verify-email", {"token": outbox.context["token"]})
    assert verified.json() == {"state": "pending_approval"}


def applicant(portal: Portal, email: str) -> User:
    return portal.db.scalars(select(User).where(User.email == email)).one()


def pending_request_id(portal: Portal, email: str) -> str:
    statement = select(SignupRequest.id).where(
        SignupRequest.user_id == applicant(portal, email).id,
        SignupRequest.status == "pending",
    )
    return str(portal.db.scalars(statement).one())


def roles_of(body: object) -> list[str]:
    assert isinstance(body, dict)
    roles = body["roles"]
    assert isinstance(roles, list)
    return [str(role) for role in roles]


def login(portal: Portal, email: str) -> dict[str, object]:
    response = portal.anonymous("/auth/login", {"email": email, "password": PASSWORD})
    body = response.json()
    assert isinstance(body, dict)
    return {"status": response.status_code, **body}


def test_super_admin_approves_then_deactivates_an_admin(portal: Portal) -> None:
    sign_up_and_verify(portal, APPLICANT, "admin")
    identifier = pending_request_id(portal, APPLICANT)
    approve = {"approved_role": "admin", "approved_department": "ADM"}

    by_admin = portal.post("priya", f"/signup-requests/{identifier}/approve", approve)
    assert by_admin.status_code == 403
    approved = portal.ok(portal.post("karan", f"/signup-requests/{identifier}/approve", approve))
    assert approved["status"] == "approved"
    assert approved["approved_role"] == "admin"

    signed_in = login(portal, APPLICANT)
    assert signed_in["status"] == 200
    assert "admin" in roles_of(field(signed_in, "user"))

    new_admin = applicant(portal, APPLICANT)
    by_peer = portal.post("priya", f"/users/{new_admin.id}/deactivate", {"reason": "Not needed"})
    assert by_peer.status_code == 403
    result = portal.ok(
        portal.post("karan", f"/users/{new_admin.id}/deactivate", {"reason": "Left the company"})
    )
    assert result["result"] == "deactivated"
    refused = portal.anonymous("/auth/login", {"email": APPLICANT, "password": PASSWORD})
    assert refused.status_code == 403
    assert error_code(refused) == "account_state"
    assert field(refused.json(), "error", "details", "state") == "deactivated"
    assert {"signup_approved", "user_deactivated"} <= set(portal.audit_actions())


def test_super_admin_promotes_and_demotes_an_admin(portal: Portal) -> None:
    omar = portal.org["omar"]
    promoted = portal.ok(portal.post("karan", "/admins", {"user_id": str(omar.id)}))
    assert roles_of(promoted) == ["employee", "admin"]
    assert portal.get("omar", "/audit").status_code == 200
    demoted = portal.ok(portal.delete("karan", f"/admins/{omar.id}"))
    assert roles_of(demoted) == ["employee"]
    assert portal.get("omar", "/audit").status_code == 403
