from sqlalchemy import select

from app.models import EmailOutbox, SignupRequest, User
from tests.scenarios.helpers import PASSWORD, Portal, error_code, field

EMAIL = "new.joiner@ibotix.ai"
SIGNUP = {
    "name": "New Joiner",
    "email": EMAIL,
    "password": PASSWORD,
    "requested_role": "employee",
    "requested_department": "HR",
}


def login_state(portal: Portal) -> object:
    response = portal.anonymous("/auth/login", {"email": EMAIL, "password": PASSWORD})
    if response.status_code == 200:
        return "active"
    assert response.status_code == 403
    assert error_code(response) == "account_state"
    return field(response.json(), "error", "details", "state")


def pending_id(portal: Portal) -> str:
    user = portal.db.scalars(select(User).where(User.email == EMAIL)).one()
    statement = select(SignupRequest.id).where(
        SignupRequest.user_id == user.id, SignupRequest.status == "pending"
    )
    return str(portal.db.scalars(statement).one())


def verification_token(portal: Portal) -> str:
    rows = portal.db.scalars(
        select(EmailOutbox)
        .where(EmailOutbox.to_address == EMAIL, EmailOutbox.template == "verify_email")
        .order_by(EmailOutbox.created_at.desc())
    ).all()
    token = rows[0].context["token"]
    assert isinstance(token, str)
    return token


def test_signup_verify_reject_reapply_approve(portal: Portal) -> None:
    other_domain = portal.anonymous("/auth/signup", {**SIGNUP, "email": "x@gmail.com"})
    assert other_domain.status_code == 422
    assert portal.anonymous("/auth/signup", SIGNUP).status_code == 202
    assert login_state(portal) == "pending_verification"

    verified = portal.anonymous("/auth/verify-email", {"token": verification_token(portal)})
    assert verified.json() == {"state": "pending_approval"}
    assert login_state(portal) == "pending_approval"
    queue = portal.ok(portal.get("priya", "/signup-requests?status=pending"))
    assert queue["total"] == 1

    reject = portal.ok(
        portal.post(
            "priya",
            f"/signup-requests/{pending_id(portal)}/reject",
            {"reason": "Please use your HR onboarding email"},
        )
    )
    assert reject["status"] == "rejected"
    denied = portal.anonymous("/auth/login", {"email": EMAIL, "password": PASSWORD})
    assert field(denied.json(), "error", "details", "rejection_reason") == (
        "Please use your HR onboarding email"
    )

    reapply = {
        "email": EMAIL,
        "password": PASSWORD,
        "requested_role": "employee",
        "requested_department": "HR",
    }
    wrong = portal.anonymous("/auth/reapply", {**reapply, "password": "Wrong-Password-1"})
    assert wrong.status_code == 403
    assert portal.anonymous("/auth/reapply", reapply).status_code == 202
    assert login_state(portal) == "pending_approval"

    approve = {"approved_role": "employee", "approved_department": "HR"}
    by_self = portal.post("priya", f"/signup-requests/{pending_id(portal)}/approve", approve)
    assert by_self.status_code == 200
    assert login_state(portal) == "active"
    actions = set(portal.audit_actions())
    assert {
        "signup_requested",
        "email_verified",
        "signup_rejected",
        "signup_reapplied",
        "signup_approved",
    } <= actions


def test_nobody_approves_their_own_request(portal: Portal) -> None:
    body = {**SIGNUP, "email": "self.approver@ibotix.ai", "requested_role": "super_admin"}
    assert portal.anonymous("/auth/signup", body).status_code == 202
    rows = portal.db.scalars(
        select(EmailOutbox).where(EmailOutbox.to_address == "self.approver@ibotix.ai")
    ).all()
    token = rows[0].context["token"]
    portal.anonymous("/auth/verify-email", {"token": token})
    user = portal.db.scalars(select(User).where(User.email == "self.approver@ibotix.ai")).one()
    request = portal.db.scalars(select(SignupRequest).where(SignupRequest.user_id == user.id)).one()
    approve = {"approved_role": "super_admin", "approved_department": "HR"}
    assert (
        portal.post("priya", f"/signup-requests/{request.id}/approve", approve).status_code == 403
    )
    assert (
        portal.post("karan", f"/signup-requests/{request.id}/approve", approve).status_code == 200
    )
