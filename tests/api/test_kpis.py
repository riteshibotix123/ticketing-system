from collections.abc import Mapping
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.enums import Priority, TicketStatus
from app.core.security import create_access_token
from app.models import Department, Ticket, TimerKind, User
from tests.factories import (
    FACTORY_NOW,
    TicketWorld,
    make_category,
    make_department,
    make_escalation_event,
    make_ticket,
    make_ticket_event,
    make_ticket_world,
    make_timer,
    make_user,
)

KPIS = "/api/v1/reports/kpis"
DASHBOARD = "/api/v1/dashboard"
EARLIER = FACTORY_NOW - timedelta(days=5)


@pytest.fixture
def world(db: Session) -> TicketWorld:
    return make_ticket_world(db)


@pytest.fixture
def ops(db: Session) -> Department:
    return make_department(db, "OPS", "Operations")


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def fetch(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    user: User,
    params: Mapping[str, str | list[str]] | None = None,
    path: str = KPIS,
) -> Response:
    response: Response = client.get(
        path, params=dict(params or {}), headers=bearer(db, user, clock, settings)
    )
    return response


def report(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    user: User,
    params: Mapping[str, str | list[str]] | None = None,
) -> dict[str, object]:
    response = fetch(client, db, clock, settings, user, params)
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def acknowledged(
    db: Session,
    requester: User,
    department: Department,
    after: timedelta,
    *,
    at: datetime = EARLIER,
    priority: Priority = Priority.MEDIUM,
    confidential: bool = False,
) -> Ticket:
    ticket = make_ticket(
        db,
        requester,
        department,
        status=TicketStatus.ACKNOWLEDGED,
        priority=priority,
        confidential=confidential,
        at=at,
    )
    make_ticket_event(db, ticket, action="acknowledged", at=at + after)
    return ticket


def section(body: Mapping[str, object], key: str) -> dict[str, object]:
    value = body[key]
    assert isinstance(value, dict)
    return value


def rows(body: Mapping[str, object], key: str) -> list[dict[str, object]]:
    value = body[key]
    assert isinstance(value, list)
    return value


def test_empty_window_gives_null_ratios_and_full_series(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    body = report(client, db, clock, settings, world.users["admin"])
    assert section(body, "sla_compliance") == {"met": 0, "missed": 0, "pct": None}
    assert section(body, "initial_response") == {
        "count": 0,
        "avg_seconds": None,
        "median_seconds": None,
    }
    assert section(body, "reopen") == {"resolved": 0, "reopened": 0, "rate_pct": None}
    assert section(body, "escalations") == {"l1": 0, "l2": 0, "l3": 0}
    trend = rows(body, "initial_response_trend")
    assert len(trend) == 31
    assert trend[0] == {"date": "2026-09-27", "count": 0, "avg_seconds": None}
    assert trend[-1]["date"] == "2026-10-27"
    assert [row["bucket"] for row in rows(body, "aging")] == [
        "0_2",
        "3_7",
        "8_14",
        "15_30",
        "31_plus",
    ]
    filters = section(body, "filters")
    assert filters["from"] == "2026-09-27T04:30:00Z"
    assert filters["to"] == "2026-10-27T04:30:00Z"
    assert filters["department_ids"] == ["HR", "IT"]
    assert filters["priorities"] == []
    assert body["generated_at"] == "2026-10-27T04:30:00Z"


def test_sla_compliance_initial_response_and_trend(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    requester = world.users["requester"]
    acknowledged(db, requester, world.it, timedelta(hours=1))
    acknowledged(db, requester, world.it, timedelta(hours=3))
    late = acknowledged(db, requester, world.hr, timedelta(hours=30))
    make_escalation_event(db, late, level=2, step_key="L2", at=EARLIER + timedelta(hours=24))
    make_escalation_event(db, late, level=1, step_key="L1", at=EARLIER + timedelta(hours=18))
    make_escalation_event(
        db, late, level=1, step_key="CREATION_CONTACT", at=EARLIER + timedelta(minutes=1)
    )
    make_ticket(db, requester, world.it, at=EARLIER)
    body = report(client, db, clock, settings, world.users["super_admin"])
    assert section(body, "sla_compliance") == {"met": 2, "missed": 1, "pct": 66.7}
    assert section(body, "initial_response") == {
        "count": 3,
        "avg_seconds": 40800,
        "median_seconds": 10800,
    }
    assert section(body, "escalations") == {"l1": 1, "l2": 1, "l3": 0}
    trend = {row["date"]: row for row in rows(body, "initial_response_trend")}
    assert trend["2026-10-22"] == {"date": "2026-10-22", "count": 2, "avg_seconds": 7200}
    assert trend["2026-10-23"] == {"date": "2026-10-23", "count": 1, "avg_seconds": 108000}
    departments = {row["department_id"]: row for row in rows(body, "departments")}
    assert departments["IT"]["sla_met_pct"] == 100.0
    assert departments["HR"]["sla_met_pct"] == 0.0


def test_resolution_turnaround_and_reopen_rate(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    requester = world.users["requester"]
    fixed = make_ticket(db, requester, world.it, status=TicketStatus.RESOLVED, at=EARLIER)
    make_ticket_event(db, fixed, action="resolved", at=EARLIER + timedelta(hours=10))
    bounced = make_ticket(db, requester, world.it, status=TicketStatus.REOPENED, at=EARLIER)
    make_ticket_event(db, bounced, action="resolved", at=EARLIER + timedelta(hours=4))
    make_ticket_event(db, bounced, action="reopened", at=EARLIER + timedelta(hours=6))
    old = FACTORY_NOW - timedelta(days=40)
    ancient = make_ticket(db, requester, world.it, status=TicketStatus.CLOSED, at=old)
    make_ticket_event(db, ancient, action="resolved", at=old + timedelta(days=5))
    body = report(client, db, clock, settings, world.users["admin"])
    assert section(body, "resolution_turnaround") == {
        "count": 2,
        "avg_seconds": 25200,
        "median_seconds": 25200,
    }
    assert section(body, "reopen") == {"resolved": 2, "reopened": 1, "rate_pct": 50.0}


def test_snapshot_counts_eta_breaches_and_persistent_l3(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    world: TicketWorld,
    ops: Department,
) -> None:
    requester = world.users["requester"]
    now = FACTORY_NOW
    make_ticket(db, requester, ops, status=TicketStatus.IN_PROGRESS, update_overdue=True)
    make_ticket(db, requester, ops, status=TicketStatus.RESOLVED, update_overdue=True)
    make_ticket(db, requester, ops, status=TicketStatus.ASSIGNED, eta=now - timedelta(hours=1))
    make_ticket(db, requester, ops, status=TicketStatus.ON_HOLD, eta=now - timedelta(hours=1))
    make_ticket(db, requester, ops, at=now - timedelta(hours=25))
    make_ticket(db, requester, ops, at=now - timedelta(days=10))
    make_ticket(db, requester, ops, at=now - timedelta(days=45))
    persistent = make_ticket(
        db, requester, ops, status=TicketStatus.IN_PROGRESS, escalation_level=3
    )
    timer = make_timer(db, persistent, TimerKind.PROGRESS_UPDATE, cycle=2)
    timer.level = 3
    make_escalation_event(
        db,
        persistent,
        timer_kind=TimerKind.PROGRESS_UPDATE,
        cycle=2,
        level=3,
        step_key="L3_REPEAT_1",
        at=now - timedelta(hours=2),
    )
    earlier_cycle = make_ticket(
        db, requester, ops, status=TicketStatus.IN_PROGRESS, escalation_level=3
    )
    old_timer = make_timer(db, earlier_cycle, TimerKind.PROGRESS_UPDATE, cycle=2)
    old_timer.level = 3
    make_escalation_event(
        db,
        earlier_cycle,
        timer_kind=TimerKind.PROGRESS_UPDATE,
        cycle=1,
        level=3,
        step_key="L3_REPEAT_1",
        at=now - timedelta(days=3),
    )
    make_escalation_event(
        db, earlier_cycle, timer_kind=TimerKind.ETA, level=2, at=now - timedelta(days=1)
    )
    make_escalation_event(
        db,
        earlier_cycle,
        timer_kind=TimerKind.ETA,
        level=1,
        step_key="L1",
        at=now - timedelta(days=1),
    )
    body = report(client, db, clock, settings, world.users["admin"], {"department_id": "OPS"})
    assert body["stale_count"] == 1
    assert body["overdue_eta_count"] == 1
    assert body["unacknowledged_over_24h"] == 3
    assert body["persistent_l3_count"] == 1
    assert body["eta_breach_count"] == 1
    assert {row["bucket"]: row["count"] for row in rows(body, "aging")} == {
        "0_2": 6,
        "3_7": 0,
        "8_14": 1,
        "15_30": 0,
        "31_plus": 1,
    }


def test_departments_workload_and_top_categories(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    world: TicketWorld,
    ops: Department,
) -> None:
    requester = world.users["requester"]
    busy = make_user(db, ops, name="Busy Bee")
    calm = make_user(db, ops, name="Calm Cat")
    alpha = make_category(db, ops, "Alpha")
    beta = make_category(db, ops, "Beta")
    for level in (0, 2, 3):
        make_ticket(
            db,
            requester,
            ops,
            status=TicketStatus.IN_PROGRESS,
            owner=calm,
            assignee=busy,
            escalation_level=level,
            priority=Priority.HIGH,
            category=alpha,
            at=EARLIER,
        )
    make_ticket(
        db,
        requester,
        ops,
        status=TicketStatus.ASSIGNED,
        owner=calm,
        assignee=calm,
        escalation_level=1,
        priority=Priority.LOW,
        category=beta,
        at=EARLIER,
    )
    make_ticket(db, requester, ops, at=EARLIER)
    make_ticket(db, requester, ops, status=TicketStatus.CLOSED, owner=busy, assignee=busy)
    body = report(client, db, clock, settings, world.users["admin"], {"department_id": "OPS"})
    assert rows(body, "departments") == [
        {
            "department_id": "OPS",
            "name": "Operations",
            "active": 5,
            "by_priority": {"low": 1, "medium": 1, "high": 3, "critical": 0},
            "on_track": 2,
            "warning": 1,
            "breached": 2,
            "sla_met_pct": 100.0,
        }
    ]
    workload = section(body, "workload")
    by_assignee = workload["by_assignee"]
    assert isinstance(by_assignee, list)
    assert [
        (row["user"] and row["user"]["name"], row["active"], row["breached"]) for row in by_assignee
    ] == [
        ("Busy Bee", 3, 2),
        ("Calm Cat", 1, 0),
        (None, 1, 0),
    ]
    by_owner = workload["by_owner"]
    assert isinstance(by_owner, list)
    assert [(row["user"] and row["user"]["name"], row["active"]) for row in by_owner] == [
        ("Calm Cat", 4),
        (None, 1),
    ]
    assert [(row["name"], row["count"]) for row in rows(body, "top_categories")] == [
        ("Alpha", 3),
        ("Beta", 1),
        ("Uncategorised", 1),
    ]
    assert rows(body, "top_categories")[0]["category_id"] == str(alpha.id)
    assert rows(body, "top_categories")[2]["category_id"] is None


def test_confidential_tickets_only_count_for_those_who_can_see_them(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    secret = make_ticket(
        db,
        world.users["requester"],
        world.it,
        status=TicketStatus.ACKNOWLEDGED,
        category=world.secret_category,
        at=EARLIER,
    )
    make_ticket_event(db, secret, action="acknowledged", at=EARLIER + timedelta(hours=2))
    make_escalation_event(
        db, secret, timer_kind=TimerKind.ETA, level=2, at=EARLIER + timedelta(hours=1)
    )
    admin = report(client, db, clock, settings, world.users["admin"])
    assert section(admin, "initial_response")["count"] == 0
    assert section(admin, "escalations") == {"l1": 0, "l2": 0, "l3": 0}
    assert section(admin, "sla_compliance") == {"met": 0, "missed": 0, "pct": None}
    assert rows(admin, "top_categories") == []
    granted = report(client, db, clock, settings, world.users["admin_with_grant"])
    assert section(granted, "initial_response")["count"] == 1
    super_admin = report(client, db, clock, settings, world.users["super_admin"])
    assert section(super_admin, "initial_response")["count"] == 1
    assert section(super_admin, "escalations")["l2"] == 1
    assert rows(super_admin, "top_categories")[0]["name"] == "Investigations"


def test_spoke_sees_only_their_departments(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    requester = world.users["requester"]
    acknowledged(db, requester, world.it, timedelta(hours=1))
    acknowledged(db, requester, world.hr, timedelta(hours=1))
    spoke = world.users["spoke"]
    body = report(client, db, clock, settings, spoke)
    assert section(body, "filters")["department_ids"] == ["IT"]
    assert section(body, "initial_response")["count"] == 1
    assert [row["department_id"] for row in rows(body, "departments")] == ["IT"]
    own = report(client, db, clock, settings, spoke, {"department_id": "IT"})
    assert section(own, "initial_response")["count"] == 1
    other = fetch(client, db, clock, settings, spoke, {"department_id": "HR"})
    assert other.status_code == 403
    assert other.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("who", ["requester", "unrelated", "collaborator"])
def test_employees_are_forbidden(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    world: TicketWorld,
    who: str,
) -> None:
    response = fetch(client, db, clock, settings, world.users[who])
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"from": "2026-10-20T00:00:00Z", "to": "2026-10-20T00:00:00Z"}, "to"),
        ({"from": "2026-10-21T00:00:00Z", "to": "2026-10-20T00:00:00Z"}, "to"),
        ({"from": "2025-01-01T00:00:00Z", "to": "2026-10-20T00:00:00Z"}, "from"),
        ({"department_id": "ZZ"}, "department_id"),
        ({"priority[]": "urgent"}, None),
        ({"from": "2026-10-20T00:00:00"}, "from"),
    ],
)
def test_invalid_filters_give_field_errors(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    world: TicketWorld,
    params: dict[str, str],
    field: str | None,
) -> None:
    response = fetch(client, db, clock, settings, world.users["admin"], params)
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert field is None or field in error["fields"]


def test_filters_narrow_the_ticket_set(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    requester = world.users["requester"]
    acknowledged(db, requester, world.it, timedelta(hours=1), priority=Priority.HIGH)
    acknowledged(db, requester, world.it, timedelta(hours=1), priority=Priority.LOW)
    acknowledged(db, requester, world.hr, timedelta(hours=1), priority=Priority.HIGH)
    acknowledged(
        db,
        requester,
        world.hr,
        timedelta(hours=1),
        at=FACTORY_NOW - timedelta(days=60),
    )
    admin = world.users["admin"]

    def count(params: Mapping[str, str | list[str]]) -> object:
        return section(report(client, db, clock, settings, admin, params), "initial_response")[
            "count"
        ]

    assert count({}) == 3
    assert count({"priority[]": "high"}) == 2
    assert count({"priority": ["high", "low"]}) == 3
    assert count({"department_id": "IT"}) == 2
    assert count({"department_id": "HR", "priority[]": "high"}) == 1
    assert count({"from": "2026-08-01T00:00:00Z", "to": "2026-09-01T00:00:00Z"}) == 1
    assert count({"from": "2026-08-01T00:00:00+05:30"}) == 4
    filtered = report(
        client, db, clock, settings, admin, {"department_id": "HR", "priority[]": "high"}
    )
    assert section(filtered, "filters")["department_ids"] == ["HR"]
    assert section(filtered, "filters")["priorities"] == ["high"]


def test_dashboards_use_the_same_definitions(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, world: TicketWorld
) -> None:
    requester = world.users["requester"]
    acknowledged(db, requester, world.it, timedelta(hours=1))
    late = acknowledged(db, requester, world.hr, timedelta(hours=3))
    make_escalation_event(db, late, level=2)
    fixed = make_ticket(db, requester, world.it, status=TicketStatus.REOPENED, at=EARLIER)
    make_ticket_event(db, fixed, action="resolved", at=EARLIER + timedelta(hours=2))
    make_ticket_event(db, fixed, action="reopened", at=EARLIER + timedelta(hours=3))
    admin_user = world.users["admin"]
    kpis = report(client, db, clock, settings, admin_user)
    admin = fetch(client, db, clock, settings, admin_user, path=f"{DASHBOARD}/admin").json()
    assert admin["sla_met_pct"] == section(kpis, "sla_compliance")["pct"] == 66.7
    assert admin["avg_initial_response_seconds"] == 7200
    assert admin["reopen_rate_pct"] == 100.0
    assert admin["by_department"] == [
        {
            "department_id": row["department_id"],
            "name": row["name"],
            "on_track": row["on_track"],
            "warning": row["warning"],
            "breached": row["breached"],
        }
        for row in rows(kpis, "departments")
    ]
    spoke = fetch(client, db, clock, settings, world.users["spoke"], path=f"{DASHBOARD}/spoke")
    body = spoke.json()
    assert body["sla_met_pct"] == 100.0
    assert body["avg_initial_response_seconds"] == 3600
    assert body["reopen_rate_pct"] == 100.0
    assert [row["department_id"] for row in body["by_department"]] == ["IT"]
