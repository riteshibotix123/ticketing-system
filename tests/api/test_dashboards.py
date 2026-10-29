from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import AccountState, Priority, Role, TicketStatus
from app.core.security import create_access_token
from app.models import TicketEventKind, User
from tests.factories import (
    FACTORY_NOW,
    TicketWorld,
    make_signup_request,
    make_ticket,
    make_ticket_event,
    make_ticket_world,
    make_user,
)

DASHBOARD = "/api/v1/dashboard"


@pytest.fixture
def world(db: Session) -> TicketWorld:
    return make_ticket_world(db)


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def fetch(
    client: TestClient, db: Session, clock: Clock, settings: Settings, user: User, kind: str
) -> Response:
    response: Response = client.get(
        f"{DASHBOARD}/{kind}", headers=bearer(db, user, clock, settings)
    )
    return response


def test_employee_dashboard_counts(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    me = world.users["unrelated"]
    for status in (
        TicketStatus.NEW,
        TicketStatus.IN_PROGRESS,
        TicketStatus.AWAITING_REQUESTER,
        TicketStatus.RESOLVED,
        TicketStatus.RESOLVED,
        TicketStatus.CLOSED,
        TicketStatus.CANCELLED,
    ):
        make_ticket(db, me, world.it, status=status)
    make_ticket(db, world.users["requester"], world.it, status=TicketStatus.ASSIGNED, assignee=me)
    make_ticket(db, world.users["requester"], world.it, status=TicketStatus.RESOLVED, assignee=me)
    make_ticket(
        db,
        world.users["requester"],
        world.it,
        status=TicketStatus.IN_PROGRESS,
        assignee=me,
        escalation_level=1,
    )
    make_ticket(
        db,
        world.users["requester"],
        world.it,
        status=TicketStatus.IN_PROGRESS,
        assignee=me,
        escalation_level=3,
    )
    make_ticket(
        db,
        world.users["requester"],
        world.it,
        status=TicketStatus.CLOSED,
        assignee=me,
        escalation_level=2,
    )
    payload = fetch(client, db, clock, settings, me, "employee").json()
    assert {key: value for key, value in payload.items() if isinstance(value, int)} == {
        "open": 3,
        "awaiting_my_response": 1,
        "resolved_to_confirm": 2,
        "closed": 1,
        "assigned_to_me": 3,
        "assigned_warning": 1,
        "assigned_breached": 1,
    }


def test_employee_attention_and_recent_updates(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    me = world.users["unrelated"]
    calm = make_ticket(db, me, world.it, status=TicketStatus.IN_PROGRESS, title="Calm")
    breached = make_ticket(
        db, me, world.it, status=TicketStatus.IN_PROGRESS, escalation_level=2, title="Breached"
    )
    waiting = make_ticket(db, me, world.it, status=TicketStatus.AWAITING_REQUESTER, title="Wait")
    warned = make_ticket(
        db,
        world.users["requester"],
        world.it,
        status=TicketStatus.ASSIGNED,
        assignee=me,
        escalation_level=1,
        title="Warned",
    )
    for index in range(12):
        make_ticket_event(
            db, calm, action="status_changed", at=FACTORY_NOW - timedelta(minutes=index)
        )
    make_ticket_event(
        db,
        breached,
        kind=TicketEventKind.INTERNAL_NOTE,
        action=None,
        body="secret note",
        is_public=False,
        at=FACTORY_NOW + timedelta(minutes=5),
    )
    make_ticket_event(db, world.tickets["normal"], at=FACTORY_NOW + timedelta(minutes=6))
    payload = fetch(client, db, clock, settings, me, "employee").json()
    assert [ticket["title"] for ticket in payload["attention"]] == ["Breached", "Warned", "Wait"]
    assert waiting.ticket_no in {ticket["id"] for ticket in payload["attention"]}
    assert warned.ticket_no in {ticket["id"] for ticket in payload["attention"]}
    updates = payload["recent_updates"]
    assert len(updates) == 10
    assert all(update["public"] for update in updates)
    assert updates[0]["at"] == "2026-10-27T04:30:00Z"
    assert "body" not in updates[0]
    assert updates[0]["actor"] == {"id": "system", "name": "System"}
    assert "owner" in payload["attention"][0]


def test_spoke_dashboard(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    requester = world.users["requester"]
    it = world.it
    make_ticket(db, requester, it, status=TicketStatus.NEW)
    make_ticket(db, requester, it, status=TicketStatus.IN_PROGRESS, escalation_level=1)
    make_ticket(db, requester, it, status=TicketStatus.IN_PROGRESS, escalation_level=3)
    make_ticket(db, requester, it, status=TicketStatus.IN_PROGRESS, update_overdue=True)
    make_ticket(
        db, requester, it, status=TicketStatus.ASSIGNED, eta=FACTORY_NOW - timedelta(hours=1)
    )
    make_ticket(db, requester, it, status=TicketStatus.AWAITING_REQUESTER)
    make_ticket(db, requester, it, status=TicketStatus.ON_HOLD)
    make_ticket(db, requester, it, status=TicketStatus.RESOLVED, escalation_level=0)
    make_ticket(
        db,
        requester,
        it,
        status=TicketStatus.NEW,
        category=world.secret_category,
        escalation_level=2,
    )
    make_ticket(db, requester, world.hr, status=TicketStatus.NEW, escalation_level=2)
    spoke = fetch(client, db, clock, settings, world.users["spoke"], "spoke").json()
    counts = {key: value for key, value in spoke.items() if isinstance(value, int)}
    assert counts == {
        "new_unacknowledged": 1,
        "approaching_sla": 1,
        "breached": 1,
        "stale_or_eta_overdue": 2,
        "awaiting_requester": 1,
        "on_hold": 1,
        "resolved_pending_closure": 1,
    }
    assert len(spoke["attention"]) == 6
    assert (spoke["sla_met_pct"], spoke["avg_initial_response_seconds"]) == (None, None)
    assert spoke["reopen_rate_pct"] is None
    assert spoke["by_department"] == [
        {"department_id": "IT", "name": "IT Department", "on_track": 6, "warning": 1, "breached": 1}
    ]
    assert spoke["attention"][0]["sla"] is not None
    assert all(not ticket["confidential"] for ticket in spoke["attention"])
    granted = fetch(client, db, clock, settings, world.users["spoke_with_grant"], "spoke").json()
    assert granted["new_unacknowledged"] == 2
    assert granted["breached"] == 2


@pytest.mark.parametrize("who", ["requester", "admin", "super_admin"])
def test_spoke_dashboard_needs_spoke(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    world: TicketWorld,
    who: str,
) -> None:
    response = fetch(client, db, clock, settings, world.users[who], "spoke")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_admin_dashboard(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    requester = world.users["requester"]
    make_ticket(db, requester, world.it, status=TicketStatus.IN_PROGRESS, escalation_level=3)
    make_ticket(db, requester, world.hr, status=TicketStatus.ASSIGNED, update_overdue=True)
    make_ticket(
        db,
        requester,
        world.it,
        status=TicketStatus.IN_PROGRESS,
        category=world.secret_category,
        escalation_level=2,
        priority=Priority.CRITICAL,
    )
    admin = fetch(client, db, clock, settings, world.users["admin"], "admin").json()
    assert {key: admin[key] for key in ("open_count", "breached_count", "l3_count")} == {
        "open_count": 4,
        "breached_count": 1,
        "l3_count": 1,
    }
    assert admin["stale_count"] == 1
    for key in ("sla_met_pct", "avg_initial_response_seconds", "reopen_rate_pct"):
        assert key in admin
        assert admin[key] is None
    assert admin["by_department"] == [
        {
            "department_id": "HR",
            "name": "HR Department",
            "on_track": 2,
            "warning": 0,
            "breached": 0,
        },
        {
            "department_id": "IT",
            "name": "IT Department",
            "on_track": 1,
            "warning": 0,
            "breached": 1,
        },
    ]
    assert all(not ticket["confidential"] for ticket in admin["attention"])
    super_admin = fetch(client, db, clock, settings, world.users["super_admin"], "admin").json()
    assert (super_admin["open_count"], super_admin["breached_count"]) == (6, 2)
    assert super_admin["attention"][0]["confidential"] is False
    assert len(super_admin["attention"]) == 6


@pytest.mark.parametrize("who", ["requester", "spoke"])
def test_admin_dashboard_needs_admin(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    world: TicketWorld,
    who: str,
) -> None:
    response = fetch(client, db, clock, settings, world.users[who], "admin")
    assert response.status_code == 403


def test_pending_approvals_follow_can_approve(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    def applicant(role: Role, state: AccountState = AccountState.PENDING_APPROVAL) -> User:
        user = make_user(db, world.it, state=state)
        make_signup_request(db, user, world.it, requested_role=role)
        return user

    applicant(Role.EMPLOYEE)
    applicant(Role.EMPLOYEE)
    applicant(Role.EMPLOYEE, AccountState.PENDING_VERIFICATION)
    applicant(Role.ADMIN)
    applicant(Role.SUPER_ADMIN)
    admin = fetch(client, db, clock, settings, world.users["admin"], "admin").json()
    assert admin["pending_approvals"] == 2
    super_admin = fetch(client, db, clock, settings, world.users["super_admin"], "admin").json()
    assert super_admin["pending_approvals"] == 4
