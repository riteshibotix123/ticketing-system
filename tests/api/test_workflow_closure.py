import uuid
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
from app.core.enums import Role, TicketStatus
from app.core.events import (
    DomainEvent,
    TicketCancelled,
    TicketClosed,
    TicketReopened,
    TicketResolved,
    bus,
)
from app.core.security import create_access_token
from app.models import (
    AuditLog,
    CloseReason,
    Department,
    SlaTimer,
    Ticket,
    TicketEvent,
    TimerKind,
    User,
)
from app.services.handlers import register_all
from app.services.workflow.system import close_system
from tests.factories import (
    make_collaborator,
    make_department,
    make_spoke_assignment,
    make_ticket,
    make_timer,
    make_user,
)

TICKETS = "/api/v1/tickets"
REASON = "Issue came back again"
SUMMARY = "Replaced the faulty cable"


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


def only_event(db: Session, ticket: Ticket) -> TicketEvent:
    return db.scalars(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)).one()


def only_audit(db: Session, ticket: Ticket) -> AuditLog:
    return db.scalars(select(AuditLog).where(AuditLog.ticket_id == ticket.id)).one()


def timer(db: Session, ticket: Ticket, kind: TimerKind) -> SlaTimer:
    statement = select(SlaTimer).where(SlaTimer.ticket_id == ticket.id, SlaTimer.kind == kind)
    return db.scalars(statement).one()


@pytest.mark.parametrize("name", ["assignee", "spoke", "admin"])
def test_resolve(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    name: str,
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    seen = capture(TicketResolved)
    body = {"summary": SUMMARY}
    response = post(client, db, clock, settings, getattr(team, name), ticket, "resolve", body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "resolved"
    assert payload["resolved_at"] == "2026-10-27T04:30:00Z"
    assert payload["resolution_summary"] == SUMMARY
    assert payload["sla"]["label"] == "Awaiting closure"
    event = only_event(db, ticket)
    assert (event.action, event.is_public) == ("resolved", True)
    assert only_audit(db, ticket).action == "ticket_resolved"
    assert len(seen) == 1
    assert timer(db, ticket, TimerKind.AUTO_CLOSE).stopped_at is None


def test_resolve_rules(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    for summary in ("too short", "x" * 2001):
        body = {"summary": summary}
        assert fields(post(client, db, clock, settings, team.spoke, ticket, "resolve", body)) == {
            "summary"
        }
    body = {"summary": SUMMARY}
    for user in (team.requester, team.collaborator):
        response = post(client, db, clock, settings, user, ticket, "resolve", body)
        assert error_code(response) == "forbidden"
    hidden = post(client, db, clock, settings, team.outsider, ticket, "resolve", body)
    assert hidden.status_code == 404
    waiting = ticket_in(db, team, TicketStatus.ASSIGNED)
    response = post(client, db, clock, settings, team.spoke, waiting, "resolve", body)
    assert error_code(response) == "invalid_transition"


def test_requester_never_resolves_even_as_team(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = make_ticket(
        db, team.spoke, team.it, status=TicketStatus.IN_PROGRESS, assignee=team.spoke
    )
    body = {"summary": SUMMARY}
    response = post(client, db, clock, settings, team.spoke, ticket, "resolve", body)
    assert response.status_code == 403
    assert error_code(response) == "forbidden"


def test_confirm_closure(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.RESOLVED)
    seen = capture(TicketClosed)
    body = {"rating": 5, "comment": "  Quick and friendly  "}
    response = post(client, db, clock, settings, team.requester, ticket, "confirm-closure", body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "closed"
    assert payload["closed_at"] == "2026-10-27T04:30:00Z"
    assert payload["feedback"] == {"rating": 5, "comment": "Quick and friendly"}
    assert payload["sla"]["stopped"] is True
    db.refresh(ticket)
    assert ticket.close_reason is CloseReason.CONFIRMED
    event = only_event(db, ticket)
    assert (event.action, event.is_public) == ("closed", True)
    assert only_audit(db, ticket).action == "ticket_closed"
    [closed] = seen
    assert isinstance(closed, TicketClosed)
    assert closed.reason is CloseReason.CONFIRMED


def test_confirm_closure_without_feedback(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.RESOLVED)
    response = post(client, db, clock, settings, team.requester, ticket, "confirm-closure", {})
    assert response.status_code == 200
    assert response.json()["feedback"] is None


def test_confirm_closure_rules(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.RESOLVED)
    for body in ({"rating": 0}, {"rating": 6}, {"comment": "x" * 1001}):
        assert fields(
            post(client, db, clock, settings, team.requester, ticket, "confirm-closure", body)
        ) == set(body)
    for user in (team.spoke, team.assignee, team.collaborator):
        response = post(client, db, clock, settings, user, ticket, "confirm-closure", {})
        assert error_code(response) == "forbidden"
    working = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    response = post(client, db, clock, settings, team.requester, working, "confirm-closure", {})
    assert error_code(response) == "invalid_transition"


def test_admin_close(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.RESOLVED)
    seen = capture(TicketClosed)
    body = {"reason": "Requester left the company"}
    response = post(client, db, clock, settings, team.spoke, ticket, "close", body)
    assert response.status_code == 200
    assert response.json()["status"] == "closed"
    db.refresh(ticket)
    assert ticket.close_reason is CloseReason.ADMIN
    entry = only_audit(db, ticket)
    assert (entry.action, entry.reason) == ("ticket_closed", "Requester left the company")
    [closed] = seen
    assert isinstance(closed, TicketClosed)
    assert closed.reason is CloseReason.ADMIN


def test_admin_close_rules(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.RESOLVED)
    assert fields(post(client, db, clock, settings, team.spoke, ticket, "close", {})) == {"reason"}
    body = {"reason": REASON}
    for user in (team.requester, team.assignee):
        assert error_code(post(client, db, clock, settings, user, ticket, "close", body)) == (
            "forbidden"
        )
    working = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    response = post(client, db, clock, settings, team.spoke, working, "close", body)
    assert error_code(response) == "invalid_transition"


@pytest.mark.parametrize("status", [TicketStatus.RESOLVED, TicketStatus.CLOSED])
@pytest.mark.parametrize("name", ["requester", "spoke"])
def test_reopen(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    status: TicketStatus,
    name: str,
) -> None:
    ticket = ticket_in(db, team, status)
    make_timer(db, ticket, TimerKind.AUTO_CLOSE)
    seen = capture(TicketReopened)
    response = post(
        client, db, clock, settings, getattr(team, name), ticket, "reopen", {"reason": REASON}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "reopened"
    assert payload["reopen_count"] == 1
    for key in (
        "resolved_at",
        "closed_at",
        "resolution_summary",
        "last_team_update_at",
        "eta",
        "next_checkpoint_at",
    ):
        assert payload[key] is None
    assert payload["owner"]["id"] == str(team.spoke.id)
    assert payload["assignee"]["id"] == str(team.assignee.id)
    assert payload["sla_started_at"] == "2026-10-27T04:30:00Z"
    event = only_event(db, ticket)
    assert (event.action, event.is_public) == ("reopened", True)
    assert event.data == {"previous_resolution": "Fixed"}
    assert only_audit(db, ticket).action == "ticket_reopened"
    assert len(seen) == 1
    assert timer(db, ticket, TimerKind.AUTO_CLOSE).stopped_at == clock.now()


def test_reopen_window_edges(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    late = ticket_in(db, team, TicketStatus.RESOLVED)
    edge = ticket_in(db, team, TicketStatus.RESOLVED)
    assert late.resolved_at is not None
    clock.set(late.resolved_at + timedelta(days=7, seconds=1))
    response = post(client, db, clock, settings, team.requester, late, "reopen", {"reason": REASON})
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "invalid_transition"
    assert error["details"] == {
        "reopen_count": 0,
        "max_reopens": 3,
        "reopen_window_days": 7,
        "reopen_window_ends_at": "2026-11-03T08:30:00Z",
    }
    clock.set(late.resolved_at + timedelta(days=7))
    response = post(client, db, clock, settings, team.requester, edge, "reopen", {"reason": REASON})
    assert response.status_code == 200


def test_reopen_count_limit(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = ticket_in(db, team, TicketStatus.RESOLVED)
    ticket.reopen_count = 3
    response = post(
        client, db, clock, settings, team.requester, ticket, "reopen", {"reason": REASON}
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["details"]["reopen_count"] == 3
    assert "maximum" in error["message"]


def test_reopen_rules(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    cancelled = ticket_in(db, team, TicketStatus.CANCELLED)
    response = post(
        client, db, clock, settings, team.requester, cancelled, "reopen", {"reason": REASON}
    )
    assert error_code(response) == "invalid_transition"
    assert "details" not in response.json()["error"]
    resolved = ticket_in(db, team, TicketStatus.RESOLVED)
    body = {"reason": REASON}
    for user in (team.collaborator, team.assignee):
        assert error_code(post(client, db, clock, settings, user, resolved, "reopen", body)) == (
            "forbidden"
        )
    short = {"reason": "abc"}
    assert fields(post(client, db, clock, settings, team.requester, resolved, "reopen", short)) == {
        "reason"
    }


def test_requester_cancels_new_ticket(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    ticket = make_ticket(db, team.requester, team.it)
    make_timer(db, ticket)
    seen = capture(TicketCancelled)
    body = {"reason": "No longer needed"}
    response = post(client, db, clock, settings, team.requester, ticket, "cancel", body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "cancelled"
    assert payload["sla"]["label"] == "Cancelled"
    db.refresh(ticket)
    assert ticket.cancel_reason == "No longer needed"
    event = only_event(db, ticket)
    assert (event.action, event.is_public) == ("cancelled", True)
    assert only_audit(db, ticket).action == "ticket_cancelled"
    assert len(seen) == 1
    assert timer(db, ticket, TimerKind.INITIAL_RESPONSE).stopped_at == clock.now()


@pytest.mark.parametrize(
    "status", [TicketStatus.NEW, TicketStatus.IN_PROGRESS, TicketStatus.ON_HOLD]
)
def test_team_cancels_active_ticket(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    team: Team,
    status: TicketStatus,
) -> None:
    ticket = ticket_in(db, team, status)
    response = post(client, db, clock, settings, team.admin, ticket, "cancel", {"reason": REASON})
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_rules(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, team: Team
) -> None:
    body = {"reason": REASON}
    working = ticket_in(db, team, TicketStatus.IN_PROGRESS)
    response = post(client, db, clock, settings, team.requester, working, "cancel", body)
    assert error_code(response) == "invalid_transition"
    for user in (team.collaborator, team.assignee):
        assert error_code(post(client, db, clock, settings, user, working, "cancel", body)) == (
            "forbidden"
        )
    resolved = ticket_in(db, team, TicketStatus.RESOLVED)
    response = post(client, db, clock, settings, team.spoke, resolved, "cancel", body)
    assert error_code(response) == "invalid_transition"
    assert fields(post(client, db, clock, settings, team.spoke, working, "cancel", {})) == {
        "reason"
    }


def test_close_system(db: Session, clock: FrozenClock, team: Team) -> None:
    register_all()
    seen = capture(TicketClosed)
    ticket = ticket_in(db, team, TicketStatus.RESOLVED)
    clock.advance(timedelta(days=3))
    assert close_system(db, clock, ticket.id) is True
    assert ticket.status is TicketStatus.CLOSED
    assert ticket.close_reason is CloseReason.AUTO
    assert ticket.closed_at == clock.now()
    event = only_event(db, ticket)
    assert (event.action, event.actor_id, event.is_public) == ("closed", None, True)
    entry = only_audit(db, ticket)
    assert (entry.action, entry.actor_id) == ("ticket_closed", None)
    [closed] = seen
    assert isinstance(closed, TicketClosed)
    assert (closed.actor_id, closed.reason) == (None, CloseReason.AUTO)


def test_close_system_skips_other_tickets(db: Session, clock: FrozenClock, team: Team) -> None:
    for status in (TicketStatus.IN_PROGRESS, TicketStatus.CLOSED):
        ticket = ticket_in(db, team, status)
        assert close_system(db, clock, ticket.id) is False
        assert ticket.status is status
    assert close_system(db, clock, uuid.uuid4()) is False
    assert db.scalars(select(TicketEvent)).first() is None
