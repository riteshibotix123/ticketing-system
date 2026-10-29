import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Environment, Settings
from app.core.enums import ScanStatus
from app.core.security import create_access_token
from app.integrations.storage import LocalStorage, StorageError
from app.models import Attachment, AuditLog, User
from app.services.attachments import sanitize_file_name
from tests.factories import (
    TicketWorld,
    make_department,
    make_ticket_world,
    make_user,
)

ATTACHMENTS = "/api/v1/attachments"
PDF = b"%PDF-1.4\n" + b"x" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 100
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        env=Environment.TEST,
        max_upload_bytes=1024,
        max_files_per_ticket=3,
        attachment_dir=tmp_path / "files",
    )


@pytest.fixture
def world(db: Session) -> TicketWorld:
    return make_ticket_world(db)


def bearer(db: Session, user: User, clock: Clock, settings: Settings) -> dict[str, str]:
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    return {"Authorization": f"Bearer {token}"}


def upload(
    client: TestClient,
    headers: dict[str, str],
    content: bytes = PDF,
    content_type: str = "application/pdf",
    name: str = "report.pdf",
) -> Response:
    response: Response = client.post(
        ATTACHMENTS, files={"file": (name, content, content_type)}, headers=headers
    )
    return response


def test_upload_creates_unlinked_attachment(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    user = world.users["requester"]
    response = upload(client, bearer(db, user, clock, settings))
    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "name": "report.pdf",
        "size": len(PDF),
        "mime": "application/pdf",
        "scan_status": "clean",
    }
    stored = db.scalars(select(Attachment).where(Attachment.id == body["id"])).one()
    assert stored.ticket_id is None
    assert stored.uploader_id == user.id
    assert stored.storage_key.startswith("attachments/")
    assert "report" not in stored.storage_key
    assert "storage_key" not in response.text
    assert (settings.attachment_dir / stored.storage_key).read_bytes() == PDF


@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (PNG, "image/png"),
        (b"\xff\xd8\xff\xe0" + b"x" * 10, "image/jpeg"),
        (b"PK\x03\x04" + b"x" * 10, DOCX_TYPE),
        ("hello, wörld".encode(), "text/plain"),
        (PDF, "application/pdf; charset=binary"),
    ],
)
def test_upload_accepts_allowed_types(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    world: TicketWorld,
    content: bytes,
    content_type: str,
) -> None:
    response = upload(
        client, bearer(db, world.users["requester"], clock, settings), content, content_type
    )
    assert response.status_code == 201, response.text


def test_upload_too_large(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    content = b"%PDF-" + b"x" * 1100
    response = upload(client, bearer(db, world.users["requester"], clock, settings), content)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (b"PK\x03\x04zip", "application/zip"),
        (PNG, "application/pdf"),
        (PDF, "image/png"),
        (b"MZ\x90\x00", "image/jpeg"),
        (b"text\x00with nul", "text/plain"),
        (b"\xff\xfe\xfa", "text/plain"),
        (PDF, ""),
    ],
)
def test_upload_rejects_wrong_or_mismatched_types(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    world: TicketWorld,
    content: bytes,
    content_type: str,
) -> None:
    response = upload(
        client, bearer(db, world.users["requester"], clock, settings), content, content_type
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file_type"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\evil.pdf", "evil.pdf"),
        ("C:\\Users\\me\\report.pdf", "report.pdf"),
        ("bad\x00na\x1fme\u202e.pdf", "badname.pdf"),
        ("...hidden.pdf", "hidden.pdf"),
        ("", "attachment"),
        ("   ", "attachment"),
        ("../", "attachment"),
        ("a" * 200 + ".pdf", "a" * 146 + ".pdf"),
        ("b" * 200, "b" * 150),
    ],
)
def test_sanitize_file_name(raw: str, expected: str) -> None:
    assert sanitize_file_name(raw) == expected


def test_upload_stores_sanitized_name(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    response = upload(
        client, bearer(db, world.users["requester"], clock, settings), name="../../secret/x.pdf"
    )
    assert response.json()["name"] == "x.pdf"


def test_unlinked_upload_limit(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    headers = bearer(db, world.users["requester"], clock, settings)
    for _ in range(3):
        assert upload(client, headers).status_code == 201
    response = upload(client, headers)
    assert response.status_code == 422
    assert "file" in response.json()["error"]["fields"]
    other = bearer(db, world.users["assignee"], clock, settings)
    assert upload(client, other).status_code == 201


def test_upload_requires_authentication(client: TestClient) -> None:
    assert (
        client.post(ATTACHMENTS, files={"file": ("a.pdf", PDF, "application/pdf")}).status_code
        == 401
    )


def test_local_storage_refuses_traversal(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    for key in ("../outside", "attachments/../../x", "/etc/passwd", "attachments/abc"):
        with pytest.raises(StorageError):
            storage.open(key)
    with pytest.raises(StorageError):
        storage.save(io.BytesIO(b"x"), "../evil")


def download(
    client: TestClient,
    db: Session,
    user: User,
    clock: Clock,
    settings: Settings,
    attachment_id: str,
) -> Response:
    response: Response = client.get(
        f"{ATTACHMENTS}/{attachment_id}/download", headers=bearer(db, user, clock, settings)
    )
    return response


def link(db: Session, attachment_id: str, world: TicketWorld, key: str) -> Attachment:
    attachment = db.scalars(select(Attachment).where(Attachment.id == attachment_id)).one()
    attachment.ticket_id = world.tickets[key].id
    db.flush()
    return attachment


def test_download_unlinked_only_by_uploader(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    owner = world.users["requester"]
    attachment_id = upload(client, bearer(db, owner, clock, settings)).json()["id"]
    response = download(client, db, owner, clock, settings, attachment_id)
    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-disposition"] == "attachment; filename*=UTF-8''report.pdf"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-type"].startswith("application/pdf")
    for name in ("super_admin", "admin", "assignee"):
        assert (
            download(client, db, world.users[name], clock, settings, attachment_id).status_code
            == 404
        )


def test_download_linked_follows_ticket_visibility(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    requester = world.users["requester"]
    attachment_id = upload(client, bearer(db, requester, clock, settings)).json()["id"]
    link(db, attachment_id, world, "secret")
    allowed = ("requester", "assignee", "collaborator", "spoke_with_grant", "super_admin")
    denied = ("spoke", "admin", "other_spoke", "unrelated")
    for name in allowed:
        assert (
            download(client, db, world.users[name], clock, settings, attachment_id).status_code
            == 200
        )
    for name in denied:
        response = download(client, db, world.users[name], clock, settings, attachment_id)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def test_confidential_download_is_audited(
    client: TestClient, db: Session, clock: Clock, settings: Settings, world: TicketWorld
) -> None:
    requester = world.users["requester"]
    secret_id = upload(client, bearer(db, requester, clock, settings)).json()["id"]
    normal_id = upload(client, bearer(db, requester, clock, settings), name="n.pdf").json()["id"]
    link(db, secret_id, world, "secret")
    link(db, normal_id, world, "normal")
    download(client, db, world.users["assignee"], clock, settings, secret_id)
    download(client, db, world.users["assignee"], clock, settings, normal_id)
    entries = list(db.scalars(select(AuditLog).where(AuditLog.action == "attachment_downloaded")))
    assert [str(entry.object_id) for entry in entries] == [secret_id]
    assert entries[0].is_confidential_ticket is True


@pytest.mark.parametrize("status", [ScanStatus.PENDING, ScanStatus.INFECTED])
def test_download_requires_clean_scan(
    client: TestClient,
    db: Session,
    clock: Clock,
    settings: Settings,
    world: TicketWorld,
    status: ScanStatus,
) -> None:
    requester = world.users["requester"]
    attachment_id = upload(client, bearer(db, requester, clock, settings)).json()["id"]
    attachment = link(db, attachment_id, world, "normal")
    attachment.scan_status = status
    db.flush()
    assert download(client, db, requester, clock, settings, attachment_id).status_code == 404


@pytest.mark.parametrize("attachment_id", ["not-a-uuid", "00000000-0000-4000-8000-000000000000"])
def test_download_unknown_is_404(
    client: TestClient, db: Session, clock: Clock, settings: Settings, attachment_id: str
) -> None:
    user = make_user(db, make_department(db, "IT"))
    assert download(client, db, user, clock, settings, attachment_id).status_code == 404
