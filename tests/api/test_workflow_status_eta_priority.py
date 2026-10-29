from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import Priority, Role, TicketStatus
from app.core.events import (
    DomainEvent,
    TeamUpdateRecorded,
    TicketEtaChanged,
    TicketPriorityChanged,
    TicketStatusChanged,
    bus,
)
from app.core.security import create_access_token
from app.models import (
    AuditLog,
    Department,
    SlaTimer,
    Ticket,
    TicketEvent,
    TicketEventKind,
    TimerKind,
    User,
)
from tests.factories import (
    make_collaborator,
    make_department,
    make_spoke_assignment,
    make_ticket,
    make_user,
)

TICKETS = "/api/v1/tickets"
REASON = "Vendor delayed the part"
MESSAGE = "Can you share the error screenshot?"


@dataclass(frozen=True)
class Team:
    it: Department
    requester: User
    spoke: User
    assignee: User
    collaborator: User
    admin: User
    outsider: User


@pytest.fixture
def team(db: Session) -> Team:
    it = make_department(db, "IT")
    hr = make_department(db, "HR")
    spoke = make_user(db, it, name="Sam Spoke")
    make_spoke_assignment(db, spoke, it)
    return Team(
        it=it,
        requester=make_user(db, hr, name="Rita Requester"),
        spoke=spoke,
        assignee=make_user(db, hr, name="Andy Assignee"),
        collaborator=make_user(db, hr, name="Cora Collaborator"),
        admin=make_user(db, hr, role=Role.ADMIN, name="Ada Admin"),
        outsider=make_user(db, hr, name="Otto Outsider"),
    )


def ticket_in(db: Session, team: Team, status: TicketStatus) -> Ticket:
    ticket = make_ticket(
        db, team.requester, team.it, status=status, owner=team.spoke, assignee=team.assignee
    )
    make_collaborator(db, ticket, team.collaborator)
    return ticket


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def post(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    user: User,
    ticket: Ticket,
    action: str,
    body: Mapping[str, object],
) -> Response:
    response: Response = client.post(
        f"{TICKETS}/{ticket.ticket_no}/{action}",
        json=body,
        headers=bearer(db, user, clock, settings),
    )
    return response


def error_code(response: Response) -> str:
    code = response.json()["error"]["code"]
    assert isinstance(code, str)
    return code


def fields(response: Response) -> set[str]:
    assert response.status_code == 422
    return set(response.json()["error"]["fields"])


def capture(*event_types: type[DomainEvent]) -> list[DomainEvent]:
    seen: list[DomainEvent] = []
    for event_type in event_types:
        bus.register(event_type, lambda _session, event: seen.append(event))
    return seen


def iso(clock: Clock, delta: timedelta) -> str:
    return (clock.now() + delta).isoformat().replace("+00:00", "Z")


def events_of(db: Session, ticket: Ticket) -> list[TicketEvent]:
    statement = select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)
    return list(db.scalars(statement.order_by(TicketEvent.at, TicketEvent.kind)))


def audit_actions(db: Session, ticket: Ticket) -> list[str]:
    statement = select(AuditLog.action).where(AuditLog.ticket_id == ticket.id)
    return list(db.scalars(statement))


def timer(db: Session, ticket: Ticket, kind: TimerKind) -> SlaTimer:
    statement = select(SlaTimer).where(SlaTimer.ticket_id == ticket.id, SlaTimer.kind == kind)
    return db.scalars(statement).one()


@pytest.mark.parametrize(
    "status", [TicketStatus.ACKNOWLEDGED, TicketStatus.ASSIGNED, TicketStatus.REOPENED]
)
def test_start_work(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    status: TicketStatus,
) -> None:
    ticket = ticket_in(db, team, status)
    seen = capture(TicketStatusChanged, TeamUpdateRecorded)
    body = {"status": "in_progress"}
    response = post(client, db, clock, settings, team.assignee, ticket, "status", body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "in_progress"
    assert payload["last_team_update_at"] == "2026-10-27T04:30:00Z"
    [event] = events_of(db, ticket)
    assert event.action == "status_changed"
    assert event.detail == f"Status changed from {status.value.replace('_', ' ')} to in progress"
    assert event.is_public is True
    assert audit_actions(db, ticket) == ["ticket_status_changed"]
    changed = seen[0]
    assert isinstance(changed, TicketStatusChanged)
    assert (changed.from_status, changed.to_status) == (status, TicketStatus.IN_PROGRESS)
    assert isinstance(seen[1], TeamUpdateRecorded)


def test_ask_requester_posts_public_comment(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    body = {"status": "awaiting_requester", "message": MESSAGE}
    response = post(client, db, clock, settings, team.spoke, ticket, "status", body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "awaiting_requester"
    assert payload["sla"]["paused"] is True
    db.refresh(ticket)
    assert ticket.awaiting_since == clock.now()
    events = events_of(db, ticket)
    comment = next(event for event in events if event.kind is TicketEventKind.COMMENT)
    assert (comment.body, comment.is_public, comment.actor_id) == (MESSAGE, True, team.spoke.id)
    assert {event.action for event in events} == {None, "status_changed"}
    assert timer(db, ticket, TimerKind.REQUESTER_REMINDER).stopped_at is None
    assert timer(db, ticket, TimerKind.PROGRESS_UPDATE).paused_at == clock.now()


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"status": "awaiting_requester"}, {"message"}),
        ({"status": "awaiting_requester", "message": "abc"}, {"message"}),
        ({"status": "resolved"}, {"status"}),
        ({"status": "bogus"}, {"status"}),
    ],
)
def test_status_validation(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    body: dict[str, object],
    expected: set[str],
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    assert fields(post(client, db, clock, settings, team.spoke, ticket, "status", body)) == expected


@pytest.mark.parametrize("status", [TicketStatus.AWAITING_REQUESTER, TicketStatus.ON_HOLD])
def test_resume_clears_pause_fields(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    status: TicketStatus,
) -> None:
    ticket = ticket_in(db, team, status)
    body = {"status": "in_progress"}
    response = post(client, db, clock, settings, team.assignee, ticket, "status", body)
    assert response.status_code == 200
    assert response.json()["hold"] is None
    db.refresh(ticket)
    assert ticket.status is TicketStatus.IN_PROGRESS
    assert (ticket.awaiting_since, ticket.hold_reason, ticket.hold_review_date) == (
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (TicketStatus.NEW, {"status": "in_progress"}),
        (TicketStatus.IN_PROGRESS, {"status": "in_progress"}),
        (TicketStatus.ON_HOLD, {"status": "awaiting_requester", "message": MESSAGE}),
        (TicketStatus.RESOLVED, {"status": "in_progress"}),
    ],
)
def test_status_invalid_transition(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    status: TicketStatus,
    body: dict[str, object],
) -> None:
    ticket = ticket_in(db, team, status)
    response = post(client, db, clock, settings, team.spoke, ticket, "status", body)
    assert response.status_code == 409
    assert error_code(response) == "invalid_transition"


@pytest.mark.parametrize(
    ("action", "body"),
    [
        ("status", {"status": "awaiting_requester", "message": MESSAGE}),
        ("hold", {"reason": REASON, "review_date": "2026-10-30T04:30:00Z"}),
        ("eta", {"eta": "2026-11-05T04:30:00Z", "reason": REASON}),
        ("priority", {"priority": "high", "reason": REASON}),
    ],
)
@pytest.mark.parametrize(("name", "status_code"), [("requester", 403), ("collaborator", 403)])
def test_participants_cannot_work_ticket(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    action: str,
    body: dict[str, object],
    name: str,
    status_code: int,
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    response = post(client, db, clock, settings, getattr(team, name), ticket, action, body)
    assert response.status_code == status_code
    assert error_code(response) == "forbidden"


def test_outsider_gets_not_found(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    body = {"priority": "high", "reason": REASON}
    response = post(client, db, clock, settings, team.outsider, ticket, "priority", body)
    assert response.status_code == 404
    assert error_code(response) == "not_found"


def test_hold(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    seen = capture(TicketStatusChanged, TeamUpdateRecorded)
    body = {"reason": REASON, "review_date": iso(clock, timedelta(days=3))}
    response = post(client, db, clock, settings, team.assignee, ticket, "hold", body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "on_hold"
    assert payload["hold"] == {"reason": REASON, "review_date": "2026-10-30T04:30:00Z"}
    [event] = events_of(db, ticket)
    assert event.action == "hold"
    assert event.is_public is True
    assert audit_actions(db, ticket) == ["ticket_hold"]
    assert [type(event) for event in seen] == [TicketStatusChanged, TeamUpdateRecorded]
    assert timer(db, ticket, TimerKind.HOLD_REVIEW).due_at == clock.now() + timedelta(days=3)


def test_hold_validation_and_status(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    past = {"reason": REASON, "review_date": iso(clock, timedelta(minutes=-1))}
    assert fields(post(client, db, clock, settings, team.spoke, ticket, "hold", past)) == {
        "review_date"
    }
    short = {"reason": "abc", "review_date": iso(clock, timedelta(days=1))}
    assert fields(post(client, db, clock, settings, team.spoke, ticket, "hold", short)) == {
        "reason"
    }
    held = ticket_in(db, team, TicketStatus.ON_HOLD)
    body = {"reason": REASON, "review_date": iso(clock, timedelta(days=1))}
    response = post(client, db, clock, settings, team.spoke, held, "hold", body)
    assert error_code(response) == "invalid_transition"


def test_revise_eta(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    old_eta = ticket.eta
    assert old_eta is not None
    seen = capture(TicketEtaChanged, TeamUpdateRecorded)
    new_eta = old_eta + timedelta(days=2)
    body = {"eta": new_eta.isoformat(), "reason": REASON}
    response = post(client, db, clock, settings, team.assignee, ticket, "eta", body)
    assert response.status_code == 200
    assert response.json()["eta"] == "2026-10-31T04:30:00Z"
    [event] = events_of(db, ticket)
    assert event.action == "eta_revised"
    assert event.is_public is True
    assert event.detail is not None
    assert REASON in event.detail
    assert event.public_detail is not None
    assert REASON not in event.public_detail
    changed = seen[0]
    assert isinstance(changed, TicketEtaChanged)
    assert (changed.old, changed.new, changed.is_extension, changed.reason) == (
        old_eta,
        new_eta,
        True,
        REASON,
    )
    assert isinstance(seen[1], TeamUpdateRecorded)
    assert audit_actions(db, ticket) == ["ticket_eta_revised"]
    assert timer(db, ticket, TimerKind.ETA).due_at == new_eta


def test_earlier_eta_is_not_extension(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.ASSIGNED)
    seen = capture(TicketEtaChanged)
    body = {"eta": iso(clock, timedelta(hours=3)), "reason": REASON}
    assert post(client, db, clock, settings, team.spoke, ticket, "eta", body).status_code == 200
    changed = seen[0]
    assert isinstance(changed, TicketEtaChanged)
    assert changed.is_extension is False


def test_eta_validation(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    assert ticket.eta is not None
    same = {"eta": ticket.eta.isoformat(), "reason": REASON}
    past = {"eta": iso(clock, timedelta(hours=-1)), "reason": REASON}
    short = {"eta": iso(clock, timedelta(days=1)), "reason": "abc"}
    for body, expected in ((same, {"eta"}), (past, {"eta"}), (short, {"reason"})):
        assert fields(post(client, db, clock, settings, team.spoke, ticket, "eta", body)) == (
            expected
        )
    fresh = ticket_in(db, team, TicketStatus.NEW)
    body = {"eta": iso(clock, timedelta(days=1)), "reason": REASON}
    response = post(client, db, clock, settings, team.spoke, fresh, "eta", body)
    assert error_code(response) == "invalid_transition"


def test_change_priority(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.NEW)
    seen = capture(TicketPriorityChanged, TeamUpdateRecorded)
    body = {"priority": "critical", "reason": REASON}
    response = post(client, db, clock, settings, team.admin, ticket, "priority", body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["priority"] == "critical"
    assert payload["requested_priority"] == "medium"
    [event] = events_of(db, ticket)
    assert event.action == "priority_changed"
    assert event.is_public is False
    changed = seen[0]
    assert isinstance(changed, TicketPriorityChanged)
    assert (changed.old, changed.new) == (Priority.MEDIUM, Priority.CRITICAL)
    assert len(seen) == 1
    assert audit_actions(db, ticket) == ["ticket_priority_changed"]


def test_priority_rules(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    same = {"priority": "medium", "reason": REASON}
    assert fields(post(client, db, clock, settings, team.spoke, ticket, "priority", same)) == {
        "priority"
    }
    missing = {"priority": "high"}
    assert fields(post(client, db, clock, settings, team.spoke, ticket, "priority", missing)) == {
        "reason"
    }
    body = {"priority": "high", "reason": REASON}
    by_assignee = post(client, db, clock, settings, team.assignee, ticket, "priority", body)
    assert error_code(by_assignee) == "forbidden"
    closed = ticket_in(db, team, TicketStatus.CLOSED)
    response = post(client, db, clock, settings, team.spoke, closed, "priority", body)
    assert error_code(response) == "invalid_transition"


def test_requester_timeline_hides_priority_change(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    body = {"priority": "high", "reason": REASON}
    assert (
        post(client, db, clock, settings, team.spoke, ticket, "priority", body).status_code == 200
    )
    eta = {"eta": iso(clock, timedelta(days=5)), "reason": REASON}
    assert post(client, db, clock, settings, team.spoke, ticket, "eta", eta).status_code == 200
    response = client.get(
        f"{TICKETS}/{ticket.ticket_no}/timeline",
        headers=bearer(db, team.requester, clock, settings),
    )
    assert response.status_code == 200
    timeline = response.json()
    assert [event["action"] for event in timeline] == ["eta_revised"]
    assert REASON not in timeline[0]["detail"]
