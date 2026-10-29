import io
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Connection, Engine, select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Environment, Settings
from app.core.enums import ProtectedActionKind, Role
from app.core.security import create_access_token
from app.integrations.storage import build_storage
from app.main import create_app
from app.models import (
    Attachment,
    Category,
    ConfidentialGrant,
    Department,
    PolicyVersion,
    ProtectedActionRequest,
    SignupRequest,
    Ticket,
    User,
)
from app.seed.data import SEED_PASSWORD, email_for
from app.seed.run import seed
from tests.conftest import BACKEND_ROOT, FROZEN_NOW
from tests.factories import make_attachment, make_policy_version, make_protected_action, make_user

API: Final = "/api/v1"
ORIGIN: Final = "http://localhost:5173"
ACTORS: Final = ("anonymous", "employee", "spoke", "admin", "super_admin", "admin_toggle_off")
ACTOR_NAMES: Final = {
    "employee": "Asha Verma",
    "spoke": "Rohan Mehta",
    "admin": "Priya Nair",
    "super_admin": "Karan Shah",
    "admin_toggle_off": "Priya Nair",
}
OUTCOMES: Final = {"U": "401", "F": "403", "H": "404", "A": "allowed"}
TICKET_TITLE: Final = "Excel add-in crashes on startup"
EXTRA_SUPER_ADMIN: Final = "zed.super@ibotix.ai"
REASON: Final = "Reviewed by the access matrix"


@dataclass(frozen=True, slots=True)
class World:
    ids: Mapping[str, str]
    policy: Mapping[str, object]

    def __getitem__(self, key: str) -> str:
        return self.ids[key]


@dataclass(frozen=True, slots=True)
class Call:
    path: str
    body: object = None
    files: Mapping[str, tuple[str, bytes, str]] | None = None


type Builder = Callable[[World], Call]


def fixed(path: str, body: object = None) -> Builder:
    return lambda _world: Call(path, body)


def on_ticket(action: str, body: object) -> Builder:
    return lambda w: Call(f"/tickets/{w['ticket']}/{action}", body)


def future(hours: int) -> str:
    return (FROZEN_NOW + timedelta(hours=hours)).isoformat()


MATRIX: Final[Mapping[str, tuple[Builder, str]]] = {
    "GET /api/v1/public/config": (fixed("/public/config"), "AAAAAA"),
    "POST /api/v1/auth/signup": (
        fixed(
            "/auth/signup",
            {
                "name": "Matrix Applicant",
                "email": "matrix.applicant@ibotix.ai",
                "password": "Matrix-Applicant-42",
                "requested_role": "employee",
                "requested_department": "IT",
            },
        ),
        "AAAAAA",
    ),
    "POST /api/v1/auth/verify-email": (fixed("/auth/verify-email", {"token": "x"}), "AAAAAA"),
    "POST /api/v1/auth/resend-verification": (
        fixed("/auth/resend-verification", {"email": email_for("Leena Das")}),
        "AAAAAA",
    ),
    "POST /api/v1/auth/reapply": (
        fixed(
            "/auth/reapply",
            {
                "email": email_for("Nitin Saxena"),
                "password": SEED_PASSWORD,
                "requested_role": "employee",
                "requested_department": "SAL",
            },
        ),
        "AAAAAA",
    ),
    "POST /api/v1/auth/login": (
        fixed("/auth/login", {"email": email_for("Asha Verma"), "password": SEED_PASSWORD}),
        "AAAAAA",
    ),
    "POST /api/v1/auth/mfa/setup": (fixed("/auth/mfa/setup", {"mfa_token": "x"}), "HHHHHH"),
    "POST /api/v1/auth/mfa/confirm": (
        fixed("/auth/mfa/confirm", {"mfa_token": "x", "code": "123456"}),
        "HHHHHH",
    ),
    "POST /api/v1/auth/mfa/verify": (
        fixed("/auth/mfa/verify", {"mfa_token": "x", "code": "123456"}),
        "HHHHHH",
    ),
    "POST /api/v1/auth/refresh": (fixed("/auth/refresh"), "UUUUUU"),
    "POST /api/v1/auth/logout": (fixed("/auth/logout"), "AAAAAA"),
    "POST /api/v1/auth/forgot-password": (
        fixed("/auth/forgot-password", {"email": email_for("Dev Patel")}),
        "AAAAAA",
    ),
    "POST /api/v1/auth/reset-password": (
        fixed("/auth/reset-password", {"token": "x", "password": "Another-Secret-42"}),
        "AAAAAA",
    ),
    "GET /api/v1/auth/me": (fixed("/auth/me"), "UAAAAA"),
    "GET /api/v1/users": (fixed("/users"), "UFFAAF"),
    "GET /api/v1/users/lookup": (fixed("/users/lookup?q=ra"), "UAAAAA"),
    "GET /api/v1/departments/{id}/members": (fixed("/departments/IT/members"), "UAAAAA"),
    "PATCH /api/v1/users/{id}/roles": (
        lambda w: Call(f"/users/{w['tara']}/roles", {"spoke_departments": [], "reason": REASON}),
        "UFFAAF",
    ),
    "POST /api/v1/users/{id}/deactivate": (
        lambda w: Call(f"/users/{w['tara']}/deactivate", {"reason": REASON}),
        "UFFAAF",
    ),
    "POST /api/v1/users/{id}/activate": (
        lambda w: Call(f"/users/{w['gaurav']}/activate"),
        "UFFAAF",
    ),
    "GET /api/v1/signup-requests": (fixed("/signup-requests"), "UFFAAA"),
    "POST /api/v1/signup-requests/{id}/approve": (
        lambda w: Call(
            f"/signup-requests/{w['kabir_request']}/approve",
            {"approved_role": "employee", "approved_department": "ENG"},
        ),
        "UFFAAA",
    ),
    "POST /api/v1/signup-requests/{id}/reject": (
        lambda w: Call(f"/signup-requests/{w['kabir_request']}/reject", {"reason": REASON}),
        "UFFAAA",
    ),
    "GET /api/v1/admins": (fixed("/admins"), "UFFFAF"),
    "POST /api/v1/admins": (lambda w: Call("/admins", {"user_id": w["tara"]}), "UFFFAF"),
    "DELETE /api/v1/admins/{user_id}": (lambda w: Call(f"/admins/{w['priya']}"), "UFFFAF"),
    "GET /api/v1/protected-actions": (fixed("/protected-actions"), "UFFFAF"),
    "POST /api/v1/protected-actions": (
        lambda w: Call(
            "/protected-actions",
            {"kind": "deactivate_super_admin", "target_user_id": w["zed"], "reason": REASON},
        ),
        "UFFFAF",
    ),
    "POST /api/v1/protected-actions/{id}/approve": (
        lambda w: Call(f"/protected-actions/{w['protected_action']}/approve"),
        "UFFFAF",
    ),
    "POST /api/v1/protected-actions/{id}/reject": (
        lambda w: Call(f"/protected-actions/{w['protected_action']}/reject", {"reason": REASON}),
        "UFFFAF",
    ),
    "GET /api/v1/departments": (fixed("/departments"), "UAAAAA"),
    "POST /api/v1/departments": (fixed("/departments", {"id": "QA", "name": "Quality"}), "UFFAAF"),
    "PATCH /api/v1/departments/{id}": (fixed("/departments/IT", {"name": "IT Services"}), "UFFAAF"),
    "POST /api/v1/departments/{id}/spokes": (
        lambda w: Call("/departments/IT/spokes", {"user_id": w["dev"]}),
        "UFFAAF",
    ),
    "DELETE /api/v1/departments/{id}/spokes/{user_id}": (
        lambda w: Call(f"/departments/IT/spokes/{w['isha']}"),
        "UFFAAF",
    ),
    "PUT /api/v1/departments/{id}/escalation": (
        fixed("/departments/IT/escalation", {"contact_id": None}),
        "UFFAAF",
    ),
    "POST /api/v1/departments/{id}/categories": (
        fixed("/departments/IT/categories", {"name": "Peripherals", "confidential": False}),
        "UFFAAF",
    ),
    "PATCH /api/v1/categories/{id}": (
        lambda w: Call(f"/categories/{w['it_hardware']}", {"name": "Hardware & Devices"}),
        "UFFAAF",
    ),
    "DELETE /api/v1/categories/{id}": (
        lambda w: Call(f"/categories/{w['it_hardware']}"),
        "UFFAAF",
    ),
    "GET /api/v1/confidential-grants": (fixed("/confidential-grants"), "UFFFAF"),
    "POST /api/v1/confidential-grants": (
        lambda w: Call(
            "/confidential-grants", {"user_id": w["aarav"], "category_id": w["legal_contracts"]}
        ),
        "UFFFAF",
    ),
    "DELETE /api/v1/confidential-grants/{id}": (
        lambda w: Call(f"/confidential-grants/{w['neha_grant']}"),
        "UFFFAF",
    ),
    "GET /api/v1/policy": (fixed("/policy"), "UFFAAA"),
    "PUT /api/v1/policy": (lambda w: Call("/policy", dict(w.policy)), "UFFFAF"),
    "GET /api/v1/me/notification-preferences": (
        fixed("/me/notification-preferences"),
        "UAAAAA",
    ),
    "PUT /api/v1/me/notification-preferences": (
        fixed("/me/notification-preferences", {"non_critical_email": "off", "digest_hour": 8}),
        "UAAAAA",
    ),
    "GET /api/v1/calendar": (fixed("/calendar"), "UFFAAA"),
    "PUT /api/v1/calendar": (
        fixed(
            "/calendar",
            {"working_days": [1, 2, 3, 4, 5], "work_start": "09:30", "work_end": "18:00"},
        ),
        "UFFFAF",
    ),
    "POST /api/v1/calendar/holidays": (
        fixed("/calendar/holidays", {"date": "2026-11-09", "name": "Diwali"}),
        "UFFFAF",
    ),
    "DELETE /api/v1/calendar/holidays/{date}": (fixed("/calendar/holidays/2026-12-25"), "UFFFHF"),
    "GET /api/v1/tickets": (fixed("/tickets"), "UAAAAA"),
    "POST /api/v1/tickets": (
        lambda w: Call(
            "/tickets",
            {
                "department_id": "IT",
                "category_id": w["it_hardware"],
                "title": "Matrix ticket",
                "description": "Raised by the authorization matrix",
                "priority": "low",
            },
        ),
        "UAAAAA",
    ),
    "GET /api/v1/tickets/{id}": (lambda w: Call(f"/tickets/{w['ticket']}"), "UHAAAA"),
    "GET /api/v1/tickets/{id}/timeline": (
        lambda w: Call(f"/tickets/{w['ticket']}/timeline"),
        "UHAAAA",
    ),
    "POST /api/v1/tickets/{id}/comments": (
        lambda w: Call(f"/tickets/{w['ticket']}/comments", {"body": "Checking in"}),
        "UHAAAA",
    ),
    "POST /api/v1/tickets/{id}/acknowledge": (
        lambda w: Call(f"/tickets/{w['ticket']}/acknowledge", {"eta": future(48)}),
        "UHAAAA",
    ),
    "POST /api/v1/tickets/{id}/assign": (
        lambda w: Call(
            f"/tickets/{w['ticket']}/assign", {"assignee_id": w["isha"], "reason": REASON}
        ),
        "UHAAAA",
    ),
    "POST /api/v1/tickets/{id}/transfer": (
        lambda w: Call(
            f"/tickets/{w['ticket']}/transfer",
            {"department_id": "HR", "category_id": w["hr_payroll"], "reason": REASON},
        ),
        "UHAAAA",
    ),
    "POST /api/v1/tickets/{id}/priority": (
        on_ticket("priority", {"priority": "critical", "reason": REASON}),
        "UHAAAA",
    ),
    "POST /api/v1/tickets/{id}/eta": (
        lambda w: Call(f"/tickets/{w['ticket']}/eta", {"eta": future(96), "reason": REASON}),
        "UHAAAA",
    ),
    "POST /api/v1/tickets/{id}/status": (
        lambda w: Call(f"/tickets/{w['ticket']}/status", {"status": "in_progress"}),
        "UHAAAA",
    ),
    "POST /api/v1/tickets/{id}/hold": (
        on_ticket("hold", {"reason": REASON, "review_date": future(72)}),
        "UHAAAA",
    ),
    "POST /api/v1/tickets/{id}/resolve": (
        lambda w: Call(f"/tickets/{w['ticket']}/resolve", {"summary": "Fixed by the matrix run"}),
        "UHAAAA",
    ),
    "POST /api/v1/tickets/{id}/confirm-closure": (
        lambda w: Call(f"/tickets/{w['ticket']}/confirm-closure", {}),
        "UHFFFF",
    ),
    "POST /api/v1/tickets/{id}/reopen": (
        lambda w: Call(f"/tickets/{w['ticket']}/reopen", {"reason": REASON}),
        "UHAAAA",
    ),
    "POST /api/v1/tickets/{id}/cancel": (
        lambda w: Call(f"/tickets/{w['ticket']}/cancel", {"reason": REASON}),
        "UHAAAA",
    ),
    "POST /api/v1/tickets/{id}/close": (
        lambda w: Call(f"/tickets/{w['ticket']}/close", {"reason": REASON}),
        "UHAAAA",
    ),
    "POST /api/v1/tickets/{id}/collaborators": (
        lambda w: Call(f"/tickets/{w['ticket']}/collaborators", {"user_id": w["sanjay"]}),
        "UHAAAA",
    ),
    "DELETE /api/v1/tickets/{id}/collaborators/{user_id}": (
        lambda w: Call(f"/tickets/{w['ticket']}/collaborators/{w['isha']}"),
        "UHAAAA",
    ),
    "POST /api/v1/attachments": (
        lambda _w: Call("/attachments", files={"file": ("notes.txt", b"notes", "text/plain")}),
        "UAAAAA",
    ),
    "GET /api/v1/attachments/{id}/download": (
        lambda w: Call(f"/attachments/{w['attachment']}/download"),
        "UHAAAA",
    ),
    "GET /api/v1/notifications": (fixed("/notifications"), "UAAAAA"),
    "GET /api/v1/notifications/unread-count": (fixed("/notifications/unread-count"), "UAAAAA"),
    "POST /api/v1/notifications/{id}/read": (
        lambda _w: Call(f"/notifications/{uuid.uuid4()}/read"),
        "UHHHHH",
    ),
    "POST /api/v1/notifications/read-all": (fixed("/notifications/read-all"), "UAAAAA"),
    "GET /api/v1/audit": (fixed("/audit"), "UFFAAA"),
    "GET /api/v1/dashboard/employee": (fixed("/dashboard/employee"), "UAAAAA"),
    "GET /api/v1/dashboard/spoke": (fixed("/dashboard/spoke"), "UFAFFF"),
    "GET /api/v1/dashboard/admin": (fixed("/dashboard/admin"), "UFFAAA"),
    "GET /api/v1/reports/kpis": (fixed("/reports/kpis"), "UFAAAA"),
    "GET /api/v1/reports/export": (
        fixed("/reports/export?type=kpis&format=csv"),
        "UFAAAA",
    ),
    "GET /api/v1/saved-views": (fixed("/saved-views"), "UAAAAA"),
    "POST /api/v1/saved-views": (
        fixed("/saved-views", {"name": "Matrix view", "query": {"sla_state": "stale"}}),
        "UAAAAA",
    ),
    "PATCH /api/v1/saved-views/{id}": (
        fixed("/saved-views/builtin.escalated_l3", {"name": "Renamed"}),
        "UFFFFF",
    ),
    "DELETE /api/v1/saved-views/{id}": (
        lambda _w: Call(f"/saved-views/{uuid.uuid4()}"),
        "UHHHHH",
    ),
}

CASES: Final = [(route, index) for route in MATRIX for index in range(len(ACTORS))]


def contract_routes() -> set[str]:
    lines = (BACKEND_ROOT / "contract" / "routes.txt").read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip()}


def test_matrix_covers_every_contract_route() -> None:
    assert set(MATRIX) == contract_routes()
    assert all(len(expected) == len(ACTORS) for _, expected in MATRIX.values())


def test_matrix_covers_every_exposed_route() -> None:
    schema = create_app(Settings(env=Environment.TEST)).openapi()
    exposed = {
        f"{method.upper()} {path}"
        for path, operations in schema["paths"].items()
        if path.startswith(API)
        for method in operations
    }
    assert exposed == set(MATRIX)


def user_by_name(session: Session, name: str) -> User:
    return session.scalars(select(User).where(User.email == email_for(name))).one()


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
    adm = session.get(Department, "ADM")
    assert adm is not None
    zed = make_user(session, adm, email=EXTRA_SUPER_ADMIN, name="Zed Super", role=Role.SUPER_ADMIN)
    make_protected_action(
        session,
        zed,
        user_by_name(session, "Mira Kulkarni"),
        kind=ProtectedActionKind.DEACTIVATE_SUPER_ADMIN,
    )
    ticket = session.scalars(select(Ticket).where(Ticket.title == TICKET_TITLE)).one()
    make_attachment(session, user_by_name(session, "Meera Iyer"), ticket=ticket)
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


def category_id(session: Session, department: str, name: str) -> str:
    statement = select(Category.id).where(
        Category.department_id == department, Category.name == name
    )
    return str(session.scalars(statement).one())


def build_world(session: Session, settings: Settings) -> World:
    ticket = session.scalars(select(Ticket).where(Ticket.title == TICKET_TITLE)).one()
    attachment = session.scalars(select(Attachment).where(Attachment.ticket_id == ticket.id)).one()
    attachment.storage_key = build_storage(settings).save(io.BytesIO(b"%PDF-1.4 matrix"), "pdf")
    kabir = user_by_name(session, "Kabir Sethi")
    neha = user_by_name(session, "Neha Kapoor")
    zed = session.scalars(select(User).where(User.email == EXTRA_SUPER_ADMIN)).one()
    policy = session.scalars(select(PolicyVersion).order_by(PolicyVersion.version.desc())).first()
    assert policy is not None
    session.commit()
    names = {
        "tara": "Tara Joshi",
        "gaurav": "Gaurav Thakur",
        "priya": "Priya Nair",
        "dev": "Dev Patel",
        "isha": "Isha Gupta",
        "aarav": "Aarav Khanna",
        "sanjay": "Sanjay Rao",
    }
    ids = {key: str(user_by_name(session, name).id) for key, name in names.items()}
    ids.update(
        {
            "zed": str(zed.id),
            "ticket": ticket.ticket_no,
            "attachment": str(attachment.id),
            "kabir_request": str(
                session.scalars(
                    select(SignupRequest.id).where(SignupRequest.user_id == kabir.id)
                ).one()
            ),
            "protected_action": str(
                session.scalars(
                    select(ProtectedActionRequest.id).where(
                        ProtectedActionRequest.target_user_id == zed.id
                    )
                ).one()
            ),
            "neha_grant": str(
                session.scalars(
                    select(ConfidentialGrant.id).where(ConfidentialGrant.user_id == neha.id)
                ).one()
            ),
            "it_hardware": category_id(session, "IT", "Hardware"),
            "hr_payroll": category_id(session, "HR", "Payroll"),
            "legal_contracts": category_id(session, "LEG", "Contract Review"),
        }
    )
    return World(ids=ids, policy=dict(policy.config))


def disable_admin_management(session: Session) -> None:
    current = session.scalars(select(PolicyVersion).order_by(PolicyVersion.version.desc())).first()
    assert current is not None
    config = dict(current.config)
    config["admins_can_manage_departments"] = False
    make_policy_version(session, current.version + 1, config)
    session.commit()


def classify(response: Response) -> str:
    assert response.status_code < 500, response.text
    if response.status_code in {401, 403, 404}:
        return str(response.status_code)
    return "allowed"


def send(client: TestClient, method: str, call: Call, headers: dict[str, str]) -> Response:
    response: Response = client.request(
        method,
        f"{API}{call.path}",
        json=call.body if call.files is None else None,
        files=call.files,
        headers=headers,
    )
    return response


@pytest.mark.parametrize(
    ("route", "actor_index"), CASES, ids=[f"{route}::{ACTORS[i]}" for route, i in CASES]
)
def test_route_access(
    route: str,
    actor_index: int,
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
) -> None:
    actor = ACTORS[actor_index]
    builder, expected = MATRIX[route]
    world = build_world(db, settings)
    if actor == "admin_toggle_off":
        disable_admin_management(db)
    headers = {"Origin": ORIGIN}
    if actor != "anonymous":
        user = user_by_name(db, ACTOR_NAMES[actor])
        token = create_access_token(user.id, clock.now(), settings).token
        headers["Authorization"] = f"Bearer {token}"
    method = route.split(" ", 1)[0]
    response = send(client, method, builder(world), headers)
    assert classify(response) == OUTCOMES[expected[actor_index]], response.text
