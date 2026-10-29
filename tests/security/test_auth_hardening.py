import base64
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Final

import jwt
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.enums import AccountState, Role
from app.core.security import create_access_token, hash_password
from app.models import AuditLog, Department, User
from app.services.mfa import create_mfa_token
from tests.factories import make_department, make_user

PASSWORD: Final = "Correct-Horse-9"
PASSWORD_HASH: Final = hash_password(PASSWORD)
WRONG: Final = "Wrong-Horse-99"
API: Final = "/api/v1"
ORIGIN: Final = "http://localhost:5173"


@pytest.fixture
def it(db: Session) -> Department:
    return make_department(db, "IT", "Information Technology")


def account(
    db: Session,
    department: Department,
    email: str = "alice@ibotix.ai",
    state: AccountState = AccountState.ACTIVE,
) -> User:
    user = make_user(db, department, email=email, state=state, password_hash=PASSWORD_HASH)
    db.commit()
    return user


def post(client: TestClient, path: str, body: object) -> Response:
    response: Response = client.post(f"{API}{path}", json=body, headers={"Origin": ORIGIN})
    return response


def login(client: TestClient, email: str, password: str) -> Response:
    return post(client, "/auth/login", {"email": email, "password": password})


def error_of(response: Response) -> dict[str, object]:
    body = response.json()
    assert isinstance(body, dict)
    error = body["error"]
    assert isinstance(error, dict)
    return error


def without_request_id(response: Response) -> tuple[int, dict[str, object]]:
    error = dict(error_of(response))
    error.pop("request_id")
    return response.status_code, error


def bearer(user: User, clock: FrozenClock, settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, clock.now(), settings).token}"}


def signup_body(email: str, password: str = PASSWORD) -> dict[str, str]:
    return {
        "name": "New Person",
        "email": email,
        "password": password,
        "requested_role": "employee",
        "requested_department": "IT",
    }


def test_login_lockout_after_five_failures(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    account(db, it)
    for _ in range(5):
        assert login(client, "alice@ibotix.ai", WRONG).status_code == 401
    locked = login(client, "alice@ibotix.ai", PASSWORD)
    assert locked.status_code == 429
    error = error_of(locked)
    assert error["code"] == "too_many_attempts"
    assert error["details"] == {"retry_after_seconds": 900}
    clock.advance(timedelta(minutes=15, seconds=1))
    assert login(client, "alice@ibotix.ai", PASSWORD).status_code == 200


def test_login_rate_limits_per_email_and_ip(client: TestClient, it: Department) -> None:
    assert it.id == "IT"
    statuses = [login(client, "ghost@ibotix.ai", WRONG).status_code for _ in range(11)]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
    spread = [login(client, f"ghost{n}@ibotix.ai", WRONG) for n in range(10)]
    limited = spread[-1]
    assert limited.status_code == 429
    assert error_of(limited)["code"] == "rate_limited"


def test_signup_rate_limits(client: TestClient, it: Department) -> None:
    assert it.id == "IT"
    same = [post(client, "/auth/signup", signup_body("repeat@ibotix.ai")) for _ in range(6)]
    assert [response.status_code for response in same[:5]] == [202] * 5
    assert same[5].status_code == 429
    assert error_of(same[5])["code"] == "rate_limited"


def test_signup_rate_limit_per_ip(client: TestClient, it: Department) -> None:
    assert it.id == "IT"
    responses = [post(client, "/auth/signup", signup_body(f"p{n}@ibotix.ai")) for n in range(6)]
    assert [response.status_code for response in responses[:5]] == [202] * 5
    assert responses[5].status_code == 429


def test_resend_and_forgot_rate_limits(client: TestClient, db: Session, it: Department) -> None:
    account(db, it, "pending@ibotix.ai", AccountState.PENDING_VERIFICATION)
    account(db, it, "active@ibotix.ai")
    resend = [
        post(client, "/auth/resend-verification", {"email": "pending@ibotix.ai"}) for _ in range(4)
    ]
    assert [response.status_code for response in resend[:3]] == [202] * 3
    assert resend[3].status_code == 429
    forgot = [
        post(client, "/auth/forgot-password", {"email": "active@ibotix.ai"}) for _ in range(4)
    ]
    assert [response.status_code for response in forgot[:3]] == [202] * 3
    assert forgot[3].status_code == 429
    assert error_of(forgot[3])["code"] == "rate_limited"


def test_reapply_wrong_password_is_403_and_locks(
    client: TestClient, db: Session, it: Department
) -> None:
    account(db, it, "rejected@ibotix.ai", AccountState.REJECTED)
    body = {
        "email": "rejected@ibotix.ai",
        "password": WRONG,
        "requested_role": "employee",
        "requested_department": "IT",
    }
    for _ in range(5):
        response = post(client, "/auth/reapply", body)
        assert response.status_code == 403
        error = error_of(response)
        assert error["code"] == "forbidden"
        assert "password" in str(error["fields"])
    locked = post(client, "/auth/reapply", {**body, "password": PASSWORD})
    assert locked.status_code == 429
    assert error_of(locked)["code"] == "too_many_attempts"


def test_refresh_token_reuse_revokes_the_family(
    client: TestClient, db: Session, it: Department, clock: FrozenClock
) -> None:
    account(db, it)
    first = login(client, "alice@ibotix.ai", PASSWORD)
    original = first.cookies["refresh_token"]
    client.cookies.clear()
    rotated = client.post(
        f"{API}/auth/refresh", headers={"Origin": ORIGIN}, cookies={"refresh_token": original}
    )
    assert rotated.status_code == 200
    replacement = rotated.cookies["refresh_token"]
    client.cookies.clear()
    clock.advance(timedelta(seconds=5))
    reused = client.post(
        f"{API}/auth/refresh", headers={"Origin": ORIGIN}, cookies={"refresh_token": original}
    )
    assert reused.status_code == 401
    client.cookies.clear()
    after = client.post(
        f"{API}/auth/refresh", headers={"Origin": ORIGIN}, cookies={"refresh_token": replacement}
    )
    assert after.status_code == 401
    assert "refresh_reuse_detected" in set(db.scalars(select(AuditLog.action)))


def test_refresh_rejects_foreign_origin(client: TestClient) -> None:
    response = client.post(f"{API}/auth/refresh", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def unsigned_header() -> str:
    return base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()


def tampered_tokens(user: User, clock: FrozenClock, settings: Settings) -> dict[str, str]:
    now = int(clock.now().timestamp())
    claims = {"sub": str(user.id), "iat": now, "exp": now + 900, "jti": uuid.uuid4().hex}
    valid = create_access_token(user.id, clock.now(), settings).token
    header, payload, signature = valid.split(".")
    flipped = signature[:-2] + ("AA" if not signature.endswith("AA") else "BB")
    return {
        "wrong_secret": jwt.encode(claims, "another-secret-of-enough-length-123", "HS256"),
        "alg_none": f"{unsigned_header()}.{payload}.",
        "bad_signature": f"{header}.{payload}.{flipped}",
        "expired": jwt.encode(
            {**claims, "exp": now - 1}, settings.jwt_secret.get_secret_value(), "HS256"
        ),
        "missing_jti": jwt.encode(
            {key: value for key, value in claims.items() if key != "jti"},
            settings.jwt_secret.get_secret_value(),
            "HS256",
        ),
        "other_subject": jwt.encode(
            {**claims, "sub": str(uuid.uuid4())}, settings.jwt_secret.get_secret_value(), "HS256"
        ),
        "mfa_purpose": create_mfa_token(user.id, clock.now(), settings),
        "garbage": "not-a-jwt",
    }


def test_tampered_tokens_are_rejected(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    user = account(db, it)
    for name, token in tampered_tokens(user, clock, settings).items():
        response = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401, name
        assert error_of(response)["code"] == "unauthenticated", name
    valid = create_access_token(user.id, clock.now(), settings).token
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {valid}"}).is_success


def test_deactivated_user_token_stops_working(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    user = account(db, it)
    token = create_access_token(user.id, clock.now(), settings).token
    user.state = AccountState.DEACTIVATED
    db.commit()
    response = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "password",
    ["Short-1a", "alllowercase123", "ALLUPPERCASE123", "NoDigitsAtAllHere", "A1a" + "x" * 130],
)
def test_password_policy(client: TestClient, it: Department, password: str) -> None:
    assert it.id == "IT"
    response = post(client, "/auth/signup", signup_body("weak@ibotix.ai", password))
    assert response.status_code == 422
    assert "password" in str(error_of(response)["fields"])


def test_no_account_enumeration(client: TestClient, db: Session, it: Department) -> None:
    account(db, it, "known@ibotix.ai")
    unknown = login(client, "unknown@ibotix.ai", WRONG)
    wrong = login(client, "known@ibotix.ai", WRONG)
    assert without_request_id(unknown) == without_request_id(wrong)

    fresh = post(client, "/auth/signup", signup_body("brand.new@ibotix.ai"))
    existing = post(client, "/auth/signup", signup_body("known@ibotix.ai"))
    assert fresh.status_code == existing.status_code == 202
    assert fresh.json() == existing.json()

    for path in ("/auth/forgot-password", "/auth/resend-verification"):
        known = post(client, path, {"email": "known@ibotix.ai"})
        ghost = post(client, path, {"email": "ghost@ibotix.ai"})
        assert known.status_code == ghost.status_code == 202
        assert known.content == ghost.content

    reapply = {"password": WRONG, "requested_role": "employee", "requested_department": "IT"}
    ghost_reapply = post(client, "/auth/reapply", {**reapply, "email": "ghost@ibotix.ai"})
    known_reapply = post(client, "/auth/reapply", {**reapply, "email": "known@ibotix.ai"})
    assert without_request_id(ghost_reapply) == without_request_id(known_reapply)


def test_public_endpoints_never_return_401(client: TestClient, it: Department) -> None:
    assert it.id == "IT"
    bearer = {"Authorization": "Bearer garbage", "Origin": ORIGIN}
    calls: list[tuple[str, str, object]] = [
        ("GET", "/public/config", None),
        ("POST", "/auth/signup", signup_body("public@ibotix.ai")),
        ("POST", "/auth/verify-email", {"token": "nope"}),
        ("POST", "/auth/resend-verification", {"email": "x@ibotix.ai"}),
        (
            "POST",
            "/auth/reapply",
            {
                "email": "x@ibotix.ai",
                "password": WRONG,
                "requested_role": "employee",
                "requested_department": "IT",
            },
        ),
        ("POST", "/auth/forgot-password", {"email": "x@ibotix.ai"}),
        ("POST", "/auth/reset-password", {"token": "nope", "password": PASSWORD}),
    ]
    for method, path, body in calls:
        response = client.request(method, f"{API}{path}", json=body, headers=bearer)
        assert response.status_code != 401, path


def test_security_headers_and_no_store(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    user = account(db, it)
    headers = bearer(user, clock, settings)
    for path in ("/auth/me", "/tickets", "/public/config", "/does-not-exist"):
        response = client.get(f"{API}{path}", headers=headers)
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["X-Frame-Options"] == "DENY"
    assert client.get(f"{API}/auth/me", headers=headers).headers["Cache-Control"] == "no-store"
    assert login(client, "alice@ibotix.ai", WRONG).headers["Cache-Control"] == "no-store"
    download = client.get(f"{API}/attachments/{uuid.uuid4()}/download", headers=headers)
    assert download.headers["Cache-Control"] == "no-store"
    assert "Cache-Control" not in client.get(f"{API}/tickets", headers=headers).headers
    assert client.get("/health/live").headers["X-Frame-Options"] == "DENY"


def test_oversized_bodies_are_rejected_before_parsing(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    user = account(db, it)
    headers = bearer(user, clock, settings)
    too_big = settings.max_upload_bytes + 128 * 1024
    response = client.post(
        f"{API}/attachments",
        files={"file": ("big.txt", b"x" * too_big, "text/plain")},
        headers=headers,
    )
    assert response.status_code == 413
    assert error_of(response)["code"] == "file_too_large"

    def chunks() -> Iterator[bytes]:
        for _ in range(too_big // 65536 + 1):
            yield b"y" * 65536

    streamed = client.post(
        f"{API}/auth/login",
        content=chunks(),
        headers={"Content-Type": "application/json", "Origin": ORIGIN},
    )
    assert streamed.status_code == 413


def test_cors_allows_only_configured_origins(client: TestClient) -> None:
    allowed = client.options(
        f"{API}/auth/login",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert allowed.headers["access-control-allow-credentials"] == "true"
    denied = client.options(
        f"{API}/auth/login",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in denied.headers
    plain = client.get(f"{API}/public/config", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in plain.headers


def test_role_is_never_taken_from_the_token(
    client: TestClient, db: Session, it: Department, clock: FrozenClock, settings: Settings
) -> None:
    user = account(db, it)
    now = int(clock.now().timestamp())
    forged = jwt.encode(
        {
            "sub": str(user.id),
            "iat": now,
            "exp": now + 900,
            "jti": uuid.uuid4().hex,
            "role": Role.SUPER_ADMIN.value,
        },
        settings.jwt_secret.get_secret_value(),
        "HS256",
    )
    response = client.get(f"{API}/audit", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 403
