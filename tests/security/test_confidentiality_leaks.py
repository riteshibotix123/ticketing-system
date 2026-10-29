import io
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Connection, Engine, select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Environment, Settings
from app.core.security import create_access_token
from app.integrations.email import InMemorySender
from app.integrations.storage import build_storage
from app.models import (
    Attachment,
    AuditLog,
    DigestItem,
    EmailOutbox,
    NonCriticalEmail,
    Notification,
    NotificationPreference,
    Ticket,
    User,
)
from app.policy.actors import load_actor
from app.schemas.tickets import CommentBody
from app.seed.data import email_for
from app.seed.run import seed
from app.services.comments import CommentService
from app.worker import JobContext
from app.worker.jobs import digest
from tests.conftest import FROZEN_NOW
from tests.factories import make_attachment

API: Final = "/api/v1"
TITLE: Final = "Update personal records after a name change"
MARKER: Final = "Payslip correction marker ZETA-7781"
ATTACHMENT_NAME: Final = "zeta-payslip.pdf"
OUTSIDERS: Final = ("Aarav Khanna", "Priya Nair", "Rohan Mehta", "Meera Iyer", "Kavya Menon")
INSIDERS: Final = ("Neha Kapoor", "Karan Shah", "Asha Verma")
MISSING_TICKET: Final = "IBX-HR-2026-999999"
MISSING_ATTACHMENT: Final = "00000000-0000-4000-8000-000000000000"


@dataclass(frozen=True, slots=True)
class Secret:
    ticket_no: str
    attachment_id: str

    @property
    def needles(self) -> tuple[str, ...]:
        return (self.ticket_no, TITLE, MARKER, ATTACHMENT_NAME, self.attachment_id)


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
    clock = FrozenClock(FROZEN_NOW)
    seed(session, Settings(env=Environment.TEST), clock)
    ticket = session.scalars(select(Ticket).where(Ticket.title == TITLE)).one()
    assert ticket.confidential
    neha = load_actor(session, user_by_name(session, "Neha Kapoor").id)
    assert neha is not None
    CommentService(session, clock).add(neha, ticket.ticket_no, CommentBody(body=MARKER))
    CommentService(session, clock).add(
        neha, ticket.ticket_no, CommentBody(body=f"Internal: {MARKER}", internal=True)
    )
    attachment = make_attachment(session, user_by_name(session, "Asha Verma"), ticket=ticket)
    attachment.file_name = ATTACHMENT_NAME
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


@pytest.fixture
def secret(db: Session, settings: Settings) -> Secret:
    ticket = db.scalars(select(Ticket).where(Ticket.title == TITLE)).one()
    attachment = db.scalars(select(Attachment).where(Attachment.ticket_id == ticket.id)).one()
    attachment.storage_key = build_storage(settings).save(io.BytesIO(b"%PDF-1.4 zeta"), "pdf")
    db.commit()
    return Secret(ticket_no=ticket.ticket_no, attachment_id=str(attachment.id))


@dataclass
class Caller:
    client: TestClient
    headers: dict[str, str]

    def get(self, path: str) -> Response:
        response: Response = self.client.get(f"{API}{path}", headers=self.headers)
        return response

    def post(self, path: str, body: object) -> Response:
        response: Response = self.client.post(f"{API}{path}", json=body, headers=self.headers)
        return response


def caller(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, name: str
) -> Caller:
    token = create_access_token(user_by_name(db, name).id, clock.now(), settings).token
    return Caller(client, {"Authorization": f"Bearer {token}"})


def assert_clean(response: Response, secret: Secret, context: str) -> None:
    assert response.status_code < 500, f"{context}: {response.text}"
    for needle in secret.needles:
        assert needle not in response.text, f"{context}: body reveals {needle!r}"
        for name, value in response.headers.items():
            assert needle not in value, f"{context}: header {name} reveals {needle!r}"


def comparable(response: Response) -> tuple[int, object]:
    body = response.json()
    assert isinstance(body, dict)
    error = dict(body["error"])
    error.pop("request_id")
    return response.status_code, error


READ_PATHS: Final = (
    "/tickets",
    "/tickets?scope=assigned",
    "/tickets?scope=all&page_size=100",
    "/tickets?scope=queue&page_size=100",
    "/tickets?scope=all&confidential=true",
    "/tickets?scope=all&department_id=HR&page_size=100",
    "/notifications?page_size=100",
    "/notifications/unread-count",
    "/audit?page_size=100",
    "/dashboard/employee",
    "/dashboard/spoke",
    "/dashboard/admin",
    "/reports/kpis",
    "/reports/kpis?department_id=IT",
    "/reports/export?type=tickets&format=csv&scope=all",
    "/reports/export?type=tickets&format=csv&scope=queue",
    "/reports/export?type=tickets&format=csv&scope=mine",
    "/reports/export?type=kpis&format=csv",
    "/saved-views",
    "/departments",
    "/departments/HR/members",
    "/users/lookup?q=as",
)


@pytest.mark.parametrize("name", OUTSIDERS)
def test_outsiders_see_nothing_in_lists_counts_and_dashboards(
    name: str,
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    secret: Secret,
) -> None:
    who = caller(client, db, clock, settings, name)
    searches = [
        f"/tickets?scope=all&q={secret.ticket_no}",
        "/tickets?scope=all&q=personal%20records",
        f"/tickets?q={secret.ticket_no}",
        "/tickets?scope=queue&q=personal",
        f"/audit?ticket_id={secret.ticket_no}",
        f"/audit?q={secret.ticket_no}",
        "/audit?q=personal",
    ]
    for path in (*READ_PATHS, *searches):
        assert_clean(who.get(path), secret, f"{name} GET {path}")


@pytest.mark.parametrize("name", OUTSIDERS)
def test_hidden_ticket_matches_missing_ticket(
    name: str,
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    secret: Secret,
) -> None:
    who = caller(client, db, clock, settings, name)
    reads = ("", "/timeline")
    for suffix in reads:
        hidden = who.get(f"/tickets/{secret.ticket_no}{suffix}")
        missing = who.get(f"/tickets/{MISSING_TICKET}{suffix}")
        assert hidden.status_code == 404
        assert comparable(hidden) == comparable(missing)
        assert_clean(hidden, secret, f"{name} GET ticket{suffix}")
    writes: tuple[tuple[str, object], ...] = (
        ("/comments", {"body": "Let me in"}),
        ("/acknowledge", {"eta": "2026-12-01T00:00:00Z"}),
        ("/cancel", {"reason": "Trying to cancel"}),
        ("/collaborators", {"user_id": str(user_by_name(db, name).id)}),
    )
    for suffix, body in writes:
        hidden = who.post(f"/tickets/{secret.ticket_no}{suffix}", body)
        missing = who.post(f"/tickets/{MISSING_TICKET}{suffix}", body)
        assert comparable(hidden) == comparable(missing), suffix
        assert_clean(hidden, secret, f"{name} POST ticket{suffix}")
    hidden_file = who.get(f"/attachments/{secret.attachment_id}/download")
    missing_file = who.get(f"/attachments/{MISSING_ATTACHMENT}/download")
    assert hidden_file.status_code == 404
    assert comparable(hidden_file) == comparable(missing_file)


def test_insiders_do_see_the_ticket(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, secret: Secret
) -> None:
    for name in INSIDERS:
        who = caller(client, db, clock, settings, name)
        detail = who.get(f"/tickets/{secret.ticket_no}")
        assert detail.status_code == 200, name
        assert MARKER in who.get(f"/tickets/{secret.ticket_no}/timeline").text
        download = who.get(f"/attachments/{secret.attachment_id}/download")
        assert download.status_code == 200, name
    karan = caller(client, db, clock, settings, "Karan Shah")
    found = karan.get(f"/tickets?scope=all&q={secret.ticket_no}").json()
    assert found["total"] == 1


def aging_total(report: dict[str, object]) -> int:
    buckets = report["aging"]
    assert isinstance(buckets, list)
    return sum(int(bucket["count"]) for bucket in buckets)


def test_counts_exclude_the_ticket_until_it_becomes_visible(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings, secret: Secret
) -> None:
    priya = caller(client, db, clock, settings, "Priya Nair")
    before_dashboard = priya.get("/dashboard/admin").json()
    before_kpis = priya.get("/reports/kpis").json()
    before_list = priya.get("/tickets?scope=all").json()["total"]
    ticket = db.scalars(select(Ticket).where(Ticket.ticket_no == secret.ticket_no)).one()
    ticket.confidential = False
    db.commit()
    after_dashboard = priya.get("/dashboard/admin").json()
    after_kpis = priya.get("/reports/kpis").json()
    after_list = priya.get("/tickets?scope=all").json()["total"]
    assert after_list == before_list + 1
    assert after_dashboard["open_count"] == before_dashboard["open_count"] + 1
    assert aging_total(after_kpis) == aging_total(before_kpis) + 1
    assert secret.ticket_no in priya.get(f"/tickets?scope=all&q={secret.ticket_no}").text


@pytest.mark.parametrize("name", ["Priya Nair", "Rohan Mehta"])
def test_exports_in_every_format_leave_the_ticket_out(
    name: str,
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    secret: Secret,
) -> None:
    who = caller(client, db, clock, settings, name)
    scope = "all" if name == "Priya Nair" else "queue"
    for export_type in ("tickets", "kpis"):
        for export_format in ("csv", "xlsx", "pdf"):
            path = f"/reports/export?type={export_type}&format={export_format}&scope={scope}"
            response = who.get(path)
            assert response.status_code == 200, f"{path}: {response.text}"
            assert_clean(response, secret, f"{name} GET {path}")
    exported = db.scalars(
        select(AuditLog)
        .where(AuditLog.action == "report_exported", AuditLog.actor_id == user_by_name(db, name).id)
        .order_by(AuditLog.created_at, AuditLog.id)
    ).all()
    counts: dict[str, set[object]] = {}
    for entry in exported:
        assert isinstance(entry.new_value, dict)
        counts.setdefault(str(entry.new_value["type"]), set()).add(entry.new_value["row_count"])
        assert entry.is_security_limited is False
    assert {key: len(values) for key, values in counts.items()} == {"tickets": 1, "kpis": 1}


def test_outsiders_received_no_notifications_or_emails_about_it(
    db: Session, secret: Secret
) -> None:
    ticket = db.scalars(select(Ticket).where(Ticket.ticket_no == secret.ticket_no)).one()
    outsider_ids = [user_by_name(db, name).id for name in OUTSIDERS]
    leaked = db.scalars(
        select(Notification).where(
            Notification.ticket_id == ticket.id, Notification.user_id.in_(outsider_ids)
        )
    ).all()
    assert leaked == []
    outsider_emails = [email_for(name) for name in OUTSIDERS]
    for email in db.scalars(select(EmailOutbox).where(EmailOutbox.to_address.in_(outsider_emails))):
        content = f"{email.subject}\n{email.body_text}\n{email.body_html}"
        for needle in (secret.ticket_no, TITLE, MARKER):
            assert needle not in content, email.to_address
    insider_mail = db.scalars(
        select(EmailOutbox).where(EmailOutbox.to_address == email_for("Asha Verma"))
    ).all()
    for email in insider_mail:
        assert MARKER not in email.body_text
        assert TITLE not in email.subject


def test_digests_mask_the_ticket_for_insiders_and_drop_it_for_outsiders(
    db: Session, secret: Secret, clock: FrozenClock, settings: Settings
) -> None:
    ticket = db.scalars(select(Ticket).where(Ticket.ticket_no == secret.ticket_no)).one()
    now = clock.now()
    for name in ("Asha Verma", "Priya Nair"):
        user = user_by_name(db, name)
        db.add(
            NotificationPreference(
                user_id=user.id,
                non_critical_email=NonCriticalEmail.DAILY_DIGEST,
                digest_hour=0,
                updated_at=now,
            )
        )
        notification = Notification(
            user_id=user.id,
            ticket_id=ticket.id,
            kind="comment_added",
            text=f"{TITLE}: {MARKER}",
            critical=False,
            created_at=now,
        )
        db.add(notification)
        db.flush()
        db.add(DigestItem(user_id=user.id, notification_id=notification.id, queued_at=now))
    db.commit()
    sent = digest.run(db, JobContext(clock=clock, settings=settings, sender=InMemorySender()))
    assert sent == 1
    emails = db.scalars(select(EmailOutbox).where(EmailOutbox.template == "notification_digest"))
    [email] = list(emails)
    assert email.to_address == email_for("Asha Verma")
    content = " ".join((email.subject, email.body_text, email.body_html))
    assert TITLE not in content
    assert MARKER not in content
    assert f"Update on {secret.ticket_no}" in content
