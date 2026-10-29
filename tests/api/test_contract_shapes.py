import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from typing import Final

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Connection, Engine, select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock, get_clock
from app.core.config import Environment, Settings
from app.core.db import get_db
from app.core.enums import (
    AccountState,
    Priority,
    ProtectedActionKind,
    ProtectedActionStatus,
    Role,
    ScanStatus,
    SignupStatus,
    SlaKind,
    TicketAction,
    TicketStatus,
)
from app.core.security import create_access_token
from app.main import create_app
from app.models import Ticket, User
from app.seed.data import SEED_PASSWORD, email_for
from app.seed.run import seed
from tests.conftest import FROZEN_NOW
from tests.factories import make_department, make_email_token, make_protected_action, make_user

MAX_UPLOAD_BYTES: Final = 4096
TIMESTAMP: Final = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
API: Final = "/api/v1"

type Check = Callable[[object, str], None]


def _fail(path: str, expected: str, value: object) -> None:
    raise AssertionError(f"{path}: expected {expected}, got {value!r}")


def string(value: object, path: str) -> None:
    if not isinstance(value, str):
        _fail(path, "string", value)


def integer(value: object, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(path, "integer", value)


def number(value: object, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        _fail(path, "number", value)


def boolean(value: object, path: str) -> None:
    if not isinstance(value, bool):
        _fail(path, "boolean", value)


def timestamp(value: object, path: str) -> None:
    if not isinstance(value, str) or not TIMESTAMP.match(value):
        _fail(path, "UTC ISO 8601 timestamp ending in Z", value)


def anything(value: object, path: str) -> None:
    if value is None:
        _fail(path, "a value (optional keys are omitted, not null)", value)


def nullable(check: Check) -> Check:
    def run(value: object, path: str) -> None:
        if value is not None:
            check(value, path)

    return run


def literal(*allowed: object) -> Check:
    def run(value: object, path: str) -> None:
        if isinstance(value, bool) or value not in allowed:
            _fail(path, f"one of {allowed}", value)

    return run


def list_of(check: Check) -> Check:
    def run(value: object, path: str) -> None:
        if not isinstance(value, list):
            _fail(path, "array", value)
            return
        for index, item in enumerate(value):
            check(item, f"{path}[{index}]")

    return run


def string_map(value: object, path: str) -> None:
    if not isinstance(value, dict):
        _fail(path, "object", value)
        return
    for key, item in value.items():
        string(key, f"{path}.key")
        string(item, f"{path}.{key}")


def json_object(value: object, path: str) -> None:
    if not isinstance(value, dict):
        _fail(path, "object", value)


@dataclass(frozen=True)
class Shape:
    required: Mapping[str, Check]
    optional: Mapping[str, Check] = field(default_factory=dict)

    def extend(
        self,
        required: Mapping[str, Check] | None = None,
        optional: Mapping[str, Check] | None = None,
    ) -> "Shape":
        return Shape({**self.required, **(required or {})}, {**self.optional, **(optional or {})})

    def __call__(self, value: object, path: str) -> None:
        if not isinstance(value, dict):
            _fail(path, "object", value)
            return
        keys = set(value)
        missing = set(self.required) - keys
        unexpected = keys - set(self.required) - set(self.optional)
        assert not missing, f"{path}: missing keys {sorted(missing)}"
        assert not unexpected, f"{path}: unexpected keys {sorted(unexpected)}"
        for key, check in self.required.items():
            check(value[key], f"{path}.{key}")
        for key, check in self.optional.items():
            if key in value:
                anything(value[key], f"{path}.{key}")
                check(value[key], f"{path}.{key}")


def one_of(*shapes: Shape) -> Check:
    def run(value: object, path: str) -> None:
        failures: list[str] = []
        for shape in shapes:
            try:
                shape(value, path)
            except AssertionError as exc:
                failures.append(str(exc))
            else:
                return
        raise AssertionError(" | ".join(failures))

    return run


def values(enum: type[StrEnum]) -> tuple[str, ...]:
    return tuple(member.value for member in enum)


FLAGS: Final = (
    "tickets.create",
    "tickets.view_all",
    "tickets.view_department",
    "tickets.acknowledge",
    "tickets.assign",
    "tickets.transfer",
    "tickets.change_priority",
    "tickets.revise_eta",
    "tickets.hold",
    "tickets.resolve",
    "tickets.close_admin",
    "tickets.reopen",
    "tickets.internal_notes",
    "users.approve_employee",
    "users.approve_admin",
    "users.approve_super_admin",
    "users.manage_roles",
    "admins.manage",
    "superadmins.protect",
    "confidential.manage",
    "departments.manage",
    "policy.manage",
    "audit.view_all",
    "reports.view_org",
)

USER_REF: Final = Shape({"id": string, "name": string, "email": string}, {"title": string})
SYSTEM: Final = Shape({"id": literal("system"), "name": literal("System")})
ACTOR: Final = one_of(USER_REF, SYSTEM)
ROLE: Final = literal(*values(Role))
ME: Final = USER_REF.extend(
    {
        "roles": list_of(ROLE),
        "department_id": nullable(string),
        "spoke_departments": list_of(string),
        "permissions": list_of(literal(*FLAGS)),
        "mfa_enabled": boolean,
    },
    {"theme": literal("system", "light", "dark")},
)
SLA_MODE: Final = literal("calendar", "business")
LOGIN_SUCCESS: Final = Shape({"access_token": string, "expires_in": integer, "user": ME})
CATEGORY: Final = Shape(
    {
        "id": string,
        "department_id": string,
        "name": string,
        "confidential": boolean,
        "active": boolean,
        "sla_mode": nullable(SLA_MODE),
    }
)
DEPARTMENT: Final = Shape(
    {
        "id": string,
        "name": string,
        "active": boolean,
        "accepts_tickets": boolean,
        "spokes": list_of(USER_REF),
        "escalation_contact": nullable(USER_REF),
        "categories": list_of(CATEGORY),
        "sla_mode": nullable(SLA_MODE),
    }
)
SLA_STATE: Final = Shape(
    {
        "level": literal(0, 1, 2, 3),
        "kind": nullable(literal(*values(SlaKind))),
        "paused": boolean,
        "stopped": boolean,
        "due_at": nullable(timestamp),
        "label": string,
    }
)
ATTACHMENT: Final = Shape(
    {
        "id": string,
        "name": string,
        "size": integer,
        "mime": string,
        "scan_status": literal(*values(ScanStatus)),
    }
)
TICKET: Final = Shape(
    {
        "id": string,
        "title": string,
        "description": string,
        "department_id": string,
        "category_id": nullable(string),
        "category_name": nullable(string),
        "priority": literal(*values(Priority)),
        "requested_priority": literal(*values(Priority)),
        "status": literal(*values(TicketStatus)),
        "confidential": boolean,
        "requester": USER_REF,
        "owner": nullable(USER_REF),
        "assignee": nullable(USER_REF),
        "collaborators": list_of(USER_REF),
        "created_at": timestamp,
        "sla_started_at": timestamp,
        "acknowledged_at": nullable(timestamp),
        "eta": nullable(timestamp),
        "next_checkpoint_at": nullable(timestamp),
        "last_team_update_at": nullable(timestamp),
        "resolved_at": nullable(timestamp),
        "closed_at": nullable(timestamp),
        "reopen_count": integer,
        "hold": nullable(Shape({"reason": string, "review_date": string})),
        "resolution_summary": nullable(string),
        "feedback": nullable(Shape({"rating": nullable(integer), "comment": nullable(string)})),
        "sla": SLA_STATE,
        "allowed_actions": list_of(literal(*values(TicketAction))),
        "attachments": list_of(ATTACHMENT),
    }
)
TIMELINE_EVENT: Final = Shape(
    {
        "id": string,
        "at": timestamp,
        "actor": ACTOR,
        "type": literal("comment", "internal_note", "audit"),
        "public": boolean,
    },
    {"action": string, "detail": string, "body": string},
)
SIGNUP_REQUEST: Final = Shape(
    {
        "id": string,
        "name": string,
        "email": string,
        "email_verified": boolean,
        "requested_role": literal("employee", "admin", "super_admin"),
        "requested_department": string,
        "status": literal(*values(SignupStatus)),
        "created_at": timestamp,
        "can_approve": boolean,
    },
    {
        "approved_role": ROLE,
        "approved_department": string,
        "decided_by": USER_REF,
        "decided_at": timestamp,
        "rejection_reason": string,
    },
)
USER_LIST_ITEM: Final = USER_REF.extend(
    {
        "roles": list_of(ROLE),
        "state": literal(*values(AccountState)),
        "department_id": nullable(string),
        "spoke_departments": list_of(string),
        "last_login_at": nullable(timestamp),
        "created_at": timestamp,
    }
)
PROTECTED_ACTION: Final = Shape(
    {
        "id": string,
        "kind": literal(*values(ProtectedActionKind)),
        "target": USER_REF,
        "requested_by": USER_REF,
        "reason": string,
        "status": literal(*values(ProtectedActionStatus)),
        "created_at": timestamp,
        "expires_at": timestamp,
        "can_decide": boolean,
    },
    {"decided_by": USER_REF, "decision_reason": string},
)
CONFIDENTIAL_GRANT: Final = Shape(
    {
        "id": string,
        "user": USER_REF,
        "category": CATEGORY,
        "granted_by": USER_REF,
        "granted_at": timestamp,
    }
)
NOTIFICATION: Final = Shape(
    {
        "id": string,
        "created_at": timestamp,
        "read": boolean,
        "critical": boolean,
        "text": string,
        "kind": string,
    },
    {"ticket_id": string},
)
AUDIT_ENTRY: Final = Shape(
    {
        "id": string,
        "at": timestamp,
        "actor": ACTOR,
        "action": string,
        "object_type": string,
        "object_id": nullable(string),
    },
    {"old_value": anything, "new_value": anything, "reason": string, "detail": string},
)
PRIORITY_HOURS: Final = Shape({priority.value: number for priority in Priority})
POLICY_CONFIG: Final = Shape(
    {
        "initial_response_hours": number,
        "warning_hours": PRIORITY_HOURS,
        "l3_hours": PRIORITY_HOURS,
        "update_warning_hours": number,
        "update_cadence_hours": number,
        "eta_warning_hours": number,
        "escalation_repeat_hours": number,
        "requester_reminder_hours": number,
        "auto_close_business_days": nullable(number),
        "reopen_window_days": number,
        "max_reopens": number,
        "sla_mode": literal("calendar", "business"),
        "admins_can_manage_departments": boolean,
    }
)
PUBLIC_CONFIG: Final = Shape(
    {
        "allowed_email_domains": list_of(string),
        "departments": list_of(Shape({"id": string, "name": string})),
        "attachment_limits": Shape(
            {"max_bytes": integer, "max_files": integer, "allowed_mime_types": list_of(string)}
        ),
        "password_min_length": integer,
        "first_response_hours": number,
    }
)
DEPARTMENT_HEALTH: Final = Shape(
    {
        "department_id": string,
        "name": string,
        "on_track": integer,
        "warning": integer,
        "breached": integer,
    }
)
EMPLOYEE_DASHBOARD: Final = Shape(
    {
        "open": integer,
        "awaiting_my_response": integer,
        "resolved_to_confirm": integer,
        "closed": integer,
        "assigned_to_me": integer,
        "assigned_warning": integer,
        "assigned_breached": integer,
        "recent_updates": list_of(TIMELINE_EVENT),
        "attention": list_of(TICKET),
    }
)
DASHBOARD_KPIS: Final = {
    "sla_met_pct": nullable(number),
    "avg_initial_response_seconds": nullable(number),
    "reopen_rate_pct": nullable(number),
    "by_department": list_of(DEPARTMENT_HEALTH),
}
SPOKE_DASHBOARD: Final = Shape(
    {
        "new_unacknowledged": integer,
        "approaching_sla": integer,
        "breached": integer,
        "stale_or_eta_overdue": integer,
        "awaiting_requester": integer,
        "on_hold": integer,
        "resolved_pending_closure": integer,
        **DASHBOARD_KPIS,
        "attention": list_of(TICKET),
    }
)
ADMIN_DASHBOARD: Final = Shape(
    {
        "open_count": integer,
        "breached_count": integer,
        "l3_count": integer,
        "stale_count": integer,
        "pending_approvals": integer,
        **DASHBOARD_KPIS,
        "attention": list_of(TICKET),
    }
)
DURATION: Final = Shape(
    {"count": integer, "avg_seconds": nullable(number), "median_seconds": nullable(number)}
)
WORKLOAD_ROW: Final = Shape({"user": nullable(USER_REF), "active": integer, "breached": integer})
KPI_REPORT: Final = Shape(
    {
        "generated_at": timestamp,
        "filters": Shape(
            {
                "from": timestamp,
                "to": timestamp,
                "department_ids": list_of(string),
                "priorities": list_of(literal(*(priority.value for priority in Priority))),
            }
        ),
        "sla_compliance": Shape({"met": integer, "missed": integer, "pct": nullable(number)}),
        "initial_response": DURATION,
        "initial_response_trend": list_of(
            Shape({"date": string, "count": integer, "avg_seconds": nullable(number)})
        ),
        "resolution_turnaround": DURATION,
        "reopen": Shape({"resolved": integer, "reopened": integer, "rate_pct": nullable(number)}),
        "escalations": Shape({"l1": integer, "l2": integer, "l3": integer}),
        "eta_breach_count": integer,
        "stale_count": integer,
        "overdue_eta_count": integer,
        "unacknowledged_over_24h": integer,
        "persistent_l3_count": integer,
        "aging": list_of(
            Shape(
                {
                    "bucket": literal("0_2", "3_7", "8_14", "15_30", "31_plus"),
                    "count": integer,
                }
            )
        ),
        "departments": list_of(
            Shape(
                {
                    "department_id": string,
                    "name": string,
                    "active": integer,
                    "by_priority": Shape({priority.value: integer for priority in Priority}),
                    "on_track": integer,
                    "warning": integer,
                    "breached": integer,
                    "sla_met_pct": nullable(number),
                }
            )
        ),
        "workload": Shape(
            {"by_assignee": list_of(WORKLOAD_ROW), "by_owner": list_of(WORKLOAD_ROW)}
        ),
        "top_categories": list_of(
            Shape({"category_id": nullable(string), "name": string, "count": integer})
        ),
    }
)
SAVED_VIEW: Final = Shape(
    {
        "id": string,
        "name": string,
        "built_in": boolean,
        "query": json_object,
        "created_at": nullable(timestamp),
        "updated_at": nullable(timestamp),
    }
)
BUSINESS_CALENDAR: Final = Shape(
    {
        "timezone": literal("Asia/Kolkata"),
        "working_days": list_of(literal(1, 2, 3, 4, 5, 6, 7)),
        "work_start": string,
        "work_end": string,
        "holidays": list_of(Shape({"date": string, "name": string})),
        "updated_at": nullable(timestamp),
    }
)
NOTIFICATION_PREFERENCES: Final = Shape(
    {
        "non_critical_email": literal("immediate", "daily_digest", "off"),
        "digest_hour": integer,
        "critical_email": literal("always"),
    }
)
ERROR_ENVELOPE: Final = Shape(
    {
        "error": Shape(
            {"code": string, "message": string, "request_id": string},
            {"fields": string_map, "details": json_object},
        )
    }
)


def page_of(item: Check) -> Shape:
    return Shape({"items": list_of(item), "total": integer, "page": integer, "page_size": integer})


@pytest.fixture
def settings() -> Settings:
    return Settings(env=Environment.TEST, max_upload_bytes=MAX_UPLOAD_BYTES)


@pytest.fixture(scope="module")
def seeded_connection(migrated_engine: Engine) -> Iterator[Connection]:
    connection = migrated_engine.connect()
    outer = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    seed(session, Settings(env=Environment.TEST), FrozenClock(FROZEN_NOW))
    session.commit()
    session.close()
    yield connection
    outer.rollback()
    connection.close()


@pytest.fixture
def db(seeded_connection: Connection) -> Iterator[Session]:
    nested = seeded_connection.begin_nested()
    session = Session(
        bind=seeded_connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    yield session
    session.close()
    if nested.is_active:
        nested.rollback()


def user(db: Session, name: str) -> User:
    return db.scalars(select(User).where(User.email == email_for(name))).one()


def ticket_no(db: Session, title: str) -> str:
    return db.scalars(select(Ticket.ticket_no).where(Ticket.title == title)).one()


@dataclass
class Api:
    client: TestClient
    db: Session
    clock: FrozenClock
    settings: Settings

    def headers(self, name: str) -> dict[str, str]:
        token = create_access_token(user(self.db, name).id, self.clock.now(), self.settings)
        return {"Authorization": f"Bearer {token.token}"}

    def get(self, path: str, name: str | None = None) -> Response:
        headers = self.headers(name) if name is not None else {}
        response: Response = self.client.get(f"{API}{path}", headers=headers)
        return response

    def post(self, path: str, body: object, name: str | None = None) -> Response:
        headers = self.headers(name) if name is not None else {}
        response: Response = self.client.post(f"{API}{path}", json=body, headers=headers)
        return response

    def ok(self, path: str, name: str | None = None) -> object:
        response = self.get(path, name)
        assert response.status_code == 200, response.text
        body: object = response.json()
        return body


@pytest.fixture
def api(client: TestClient, db: Session, clock: FrozenClock, settings: Settings) -> Api:
    return Api(client, db, clock, settings)


def test_me_and_login_success(api: Api, db: Session) -> None:
    for name in ("Karan Shah", "Priya Nair", "Rohan Mehta", "Asha Verma"):
        ME(api.ok("/auth/me", name), name)
    login = api.post("/auth/login", {"email": email_for("Asha Verma"), "password": SEED_PASSWORD})
    assert login.status_code == 200
    LOGIN_SUCCESS(login.json(), "login")

    plain = make_user(db, make_department(db, "QA"), email="plain@ibotix.ai")
    db.commit()
    token = create_access_token(plain.id, api.clock.now(), api.settings).token
    body = api.client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    ME(body, "me")
    assert "title" not in body
    assert "theme" not in body


def test_public_config_and_policy(api: Api) -> None:
    PUBLIC_CONFIG(api.ok("/public/config"), "public_config")
    POLICY_CONFIG(api.ok("/policy", "Priya Nair"), "policy")
    POLICY_CONFIG(api.ok("/policy", "Karan Shah"), "policy")


def test_business_calendar(api: Api) -> None:
    for name in ("Priya Nair", "Karan Shah"):
        BUSINESS_CALENDAR(api.ok("/calendar", name), f"calendar[{name}]")
    added = api.post("/calendar/holidays", {"date": "2026-11-09", "name": "Diwali"}, "Karan Shah")
    assert added.status_code == 201, added.text
    BUSINESS_CALENDAR(added.json(), "calendar_with_holiday")


def test_notification_preferences(api: Api) -> None:
    for name in ("Asha Verma", "Karan Shah"):
        NOTIFICATION_PREFERENCES(
            api.ok("/me/notification-preferences", name), f"preferences[{name}]"
        )
    saved = api.client.put(
        f"{API}/me/notification-preferences",
        json={"non_critical_email": "daily_digest", "digest_hour": 7},
        headers=api.headers("Asha Verma"),
    )
    assert saved.status_code == 200, saved.text
    NOTIFICATION_PREFERENCES(saved.json(), "preferences_saved")


def test_departments(api: Api) -> None:
    for name in ("Karan Shah", "Asha Verma"):
        body = api.ok("/departments", name)
        list_of(DEPARTMENT)(body, "departments")
        assert isinstance(body, list)
        assert body


def test_tickets_and_sla_state(api: Api, db: Session) -> None:
    page = api.ok("/tickets?scope=all&page_size=100", "Karan Shah")
    page_of(TICKET)(page, "tickets")
    assert isinstance(page, dict)
    items = page["items"]
    assert isinstance(items, list)
    assert {item["status"] for item in items} == {status.value for status in TicketStatus}
    assert any(item["hold"] is not None for item in items)
    assert any(item["feedback"] is not None for item in items)
    for title in (
        "Excel add-in crashes on startup",
        "Additional QA engineer for the Atlas project",
    ):
        number = ticket_no(db, title)
        TICKET(api.ok(f"/tickets/{number}", "Karan Shah"), title)
    page_of(TICKET)(api.ok("/tickets", "Asha Verma"), "mine")
    page_of(TICKET)(api.ok("/tickets?scope=queue", "Rohan Mehta"), "queue")


def test_attachment_upload(api: Api) -> None:
    response = api.client.post(
        f"{API}/attachments",
        files={"file": ("notes.txt", b"plain text notes", "text/plain")},
        headers=api.headers("Asha Verma"),
    )
    assert response.status_code == 201
    ATTACHMENT(response.json(), "attachment")


def test_timeline_for_staff_and_requester(api: Api, db: Session) -> None:
    number = ticket_no(db, "Excel add-in crashes on startup")
    staff = api.ok(f"/tickets/{number}/timeline", "Rohan Mehta")
    requester = api.ok(f"/tickets/{number}/timeline", "Meera Iyer")
    list_of(TIMELINE_EVENT)(staff, "staff_timeline")
    list_of(TIMELINE_EVENT)(requester, "requester_timeline")
    assert isinstance(staff, list)
    assert isinstance(requester, list)
    assert any(event["type"] == "internal_note" for event in staff)
    assert all(event["public"] for event in requester)
    comment = api.post(
        f"/tickets/{number}/comments", {"body": "Any update?", "internal": False}, "Meera Iyer"
    )
    assert comment.status_code in {200, 201}
    TIMELINE_EVENT(comment.json(), "comment")


def test_signup_requests_users_and_admins(api: Api) -> None:
    page_of(SIGNUP_REQUEST)(api.ok("/signup-requests", "Karan Shah"), "signup_requests")
    page_of(SIGNUP_REQUEST)(api.ok("/signup-requests", "Priya Nair"), "signup_requests")
    page_of(USER_LIST_ITEM)(api.ok("/users?page_size=100", "Karan Shah"), "users")
    list_of(USER_LIST_ITEM)(api.ok("/admins", "Karan Shah"), "admins")
    list_of(USER_REF)(api.ok("/users/lookup?q=ra", "Asha Verma"), "lookup")
    list_of(USER_REF)(api.ok("/departments/IT/members", "Asha Verma"), "members")


def test_protected_actions_and_grants(api: Api, db: Session) -> None:
    make_protected_action(
        db,
        user(db, "Mira Kulkarni"),
        user(db, "Karan Shah"),
        kind=ProtectedActionKind.DEMOTE_SUPER_ADMIN,
    )
    db.commit()
    body = api.ok("/protected-actions", "Karan Shah")
    page_of(PROTECTED_ACTION)(body, "protected_actions")
    assert isinstance(body, dict)
    assert body["total"] == 1
    list_of(CONFIDENTIAL_GRANT)(api.ok("/confidential-grants", "Karan Shah"), "grants")


def test_notifications_and_audit(api: Api) -> None:
    for name in ("Rohan Mehta", "Asha Verma", "Karan Shah"):
        body = api.ok("/notifications?page_size=100", name)
        page_of(NOTIFICATION)(body, "notifications")
        Shape({"count": integer})(api.ok("/notifications/unread-count", name), "unread")
    audit = api.ok("/audit?page_size=100", "Karan Shah")
    page_of(AUDIT_ENTRY)(audit, "audit")
    assert isinstance(audit, dict)
    assert audit["total"] > 0
    page_of(AUDIT_ENTRY)(api.ok("/audit?page_size=100", "Priya Nair"), "audit_admin")


def test_dashboards(api: Api) -> None:
    EMPLOYEE_DASHBOARD(api.ok("/dashboard/employee", "Asha Verma"), "employee_dashboard")
    SPOKE_DASHBOARD(api.ok("/dashboard/spoke", "Rohan Mehta"), "spoke_dashboard")
    admin = api.ok("/dashboard/admin", "Priya Nair")
    ADMIN_DASHBOARD(admin, "admin_dashboard")
    assert isinstance(admin, dict)
    assert admin["by_department"]


def test_kpi_report(api: Api) -> None:
    for name in ("Priya Nair", "Karan Shah", "Rohan Mehta"):
        KPI_REPORT(api.ok("/reports/kpis", name), f"kpi_report[{name}]")
    filtered = api.ok(
        "/reports/kpis?department_id=IT&priority[]=high&priority[]=critical", "Priya Nair"
    )
    KPI_REPORT(filtered, "kpi_report_filtered")
    assert isinstance(filtered, dict)
    assert filtered["filters"]["department_ids"] == ["IT"]


def test_saved_views(api: Api) -> None:
    created = api.post(
        "/saved-views",
        {"name": "Breached high", "query": {"sla_state": "breached", "priority": ["high"]}},
        "Rohan Mehta",
    )
    assert created.status_code == 201, created.text
    SAVED_VIEW(created.json(), "saved_view")
    views = api.ok("/saved-views", "Rohan Mehta")
    list_of(SAVED_VIEW)(views, "saved_views")
    assert isinstance(views, list)
    assert [view["built_in"] for view in views] == [True] * 5 + [False]


def test_export_file_headers(api: Api) -> None:
    for export_format, media_type in (
        ("csv", "text/csv; charset=utf-8"),
        ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("pdf", "application/pdf"),
    ):
        response = api.get(
            f"/reports/export?type=tickets&format={export_format}&scope=all", "Priya Nair"
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == media_type
        assert re.fullmatch(
            rf'attachment; filename="ibotix-tickets-\d{{8}}-\d{{4}}\.{export_format}"',
            response.headers["content-disposition"],
        )


def expect_error(response: Response, status: int, code: str) -> dict[str, object]:
    assert response.status_code == status, response.text
    body = response.json()
    ERROR_ENVELOPE(body, code)
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    return error


def test_unauthenticated_and_invalid_credentials(api: Api) -> None:
    expect_error(api.get("/auth/me"), 401, "unauthenticated")
    bad = api.client.get(f"{API}/auth/me", headers={"Authorization": "Bearer nonsense"})
    expect_error(bad, 401, "unauthenticated")
    wrong = api.post(
        "/auth/login", {"email": email_for("Asha Verma"), "password": "Wrong-Pass-123"}
    )
    expect_error(wrong, 401, "invalid_credentials")


def test_forbidden_and_account_state(api: Api) -> None:
    expect_error(api.get("/audit", "Asha Verma"), 403, "forbidden")
    for name, state in (
        ("Kabir Sethi", "pending_approval"),
        ("Leena Das", "pending_verification"),
        ("Gaurav Thakur", "deactivated"),
        ("Nitin Saxena", "rejected"),
    ):
        response = api.post("/auth/login", {"email": email_for(name), "password": SEED_PASSWORD})
        error = expect_error(response, 403, "account_state")
        details = error["details"]
        assert isinstance(details, dict)
        assert details["state"] == state
        if state == "rejected":
            assert isinstance(details["rejection_reason"], str)


def test_not_found_is_identical_for_hidden_tickets(api: Api, db: Session) -> None:
    hidden = ticket_no(db, "Update personal records after a name change")
    missing = expect_error(api.get("/tickets/IBX-HR-2026-999999", "Aarav Khanna"), 404, "not_found")
    concealed = expect_error(api.get(f"/tickets/{hidden}", "Aarav Khanna"), 404, "not_found")
    assert {key: value for key, value in missing.items() if key != "request_id"} == {
        key: value for key, value in concealed.items() if key != "request_id"
    }
    expect_error(api.get(f"/tickets/{hidden}", "Priya Nair"), 404, "not_found")


def test_conflict_codes(api: Api, db: Session) -> None:
    expect_error(
        api.post("/departments", {"id": "IT", "name": "Duplicate"}, "Karan Shah"), 409, "conflict"
    )
    acknowledged = ticket_no(db, "Update personal records after a name change")
    cancel = api.post(
        f"/tickets/{acknowledged}/cancel", {"reason": "No longer needed"}, "Asha Verma"
    )
    expect_error(cancel, 409, "invalid_transition")
    target = user(db, "Karan Shah").id
    demote = api.client.delete(f"{API}/admins/{target}", headers=api.headers("Mira Kulkarni"))
    expect_error(demote, 409, "protected_action_blocked")


def test_token_expired(api: Api, db: Session) -> None:
    make_email_token(
        db,
        user(db, "Leena Das"),
        raw_token="expired-verification-token",
        at=FROZEN_NOW - timedelta(days=2),
    )
    db.commit()
    expect_error(
        api.post("/auth/verify-email", {"token": "expired-verification-token"}),
        410,
        "token_expired",
    )


def test_upload_errors(api: Api) -> None:
    headers = api.headers("Asha Verma")
    large = api.client.post(
        f"{API}/attachments",
        files={"file": ("big.txt", b"x" * (MAX_UPLOAD_BYTES + 1), "text/plain")},
        headers=headers,
    )
    expect_error(large, 413, "file_too_large")
    binary = api.client.post(
        f"{API}/attachments",
        files={"file": ("tool.exe", b"MZ\x90\x00binary", "application/x-msdownload")},
        headers=headers,
    )
    expect_error(binary, 415, "unsupported_file_type")


def test_validation_error(api: Api) -> None:
    error = expect_error(api.post("/tickets", {}, "Asha Verma"), 422, "validation_error")
    fields = error["fields"]
    assert isinstance(fields, dict)
    assert "title" in fields


def test_lockout_and_rate_limit(api: Api, db: Session) -> None:
    email = email_for("Meera Iyer")
    for _ in range(5):
        api.post("/auth/login", {"email": email, "password": "Wrong-Pass-123"})
    locked = expect_error(
        api.post("/auth/login", {"email": email, "password": SEED_PASSWORD}),
        429,
        "too_many_attempts",
    )
    details = locked["details"]
    assert isinstance(details, dict)
    integer(details["retry_after_seconds"], "retry_after_seconds")

    target = email_for("Dev Patel")
    responses = [api.post("/auth/forgot-password", {"email": target}) for _ in range(4)]
    assert [response.status_code for response in responses[:3]] == [202, 202, 202]
    limited = expect_error(responses[3], 429, "rate_limited")
    limited_details = limited["details"]
    assert isinstance(limited_details, dict)
    integer(limited_details["retry_after_seconds"], "retry_after_seconds")
    assert user(db, "Meera Iyer").locked_until is not None


def test_server_error(db: Session, clock: FrozenClock, settings: Settings) -> None:
    app = create_app(settings)

    def broken_db() -> Iterator[Session]:
        raise RuntimeError("database unavailable")
        yield db

    def frozen() -> Clock:
        return clock

    app.dependency_overrides[get_db] = broken_db
    app.dependency_overrides[get_clock] = frozen
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"{API}/public/config")
    error = expect_error(response, 500, "server_error")
    assert "database unavailable" not in str(error["message"])
