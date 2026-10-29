from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core import errors
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.core.request_context import REQUEST_ID_HEADER
from app.main import create_app

PROBE = "/__probe"


class Payload(BaseModel):
    title: str
    count: int


CASES: dict[str, ApiError] = {
    "unauthenticated": errors.unauthenticated(),
    "invalid_credentials": errors.invalid_credentials(),
    "forbidden": errors.forbidden(),
    "account_state": errors.account_state("rejected", "Not an employee"),
    "not_found": errors.not_found(),
    "conflict": errors.conflict(),
    "invalid_transition": errors.invalid_transition(),
    "protected_action_blocked": errors.protected_action_blocked(),
    "token_expired": errors.token_expired(),
    "file_too_large": errors.file_too_large(),
    "unsupported_file_type": errors.unsupported_file_type(),
    "validation_error": errors.validation_error({"title": "Required"}),
    "too_many_attempts": errors.too_many_attempts(120),
    "rate_limited": errors.rate_limited(10),
    "server_error": errors.server_error(),
}


def _probe_app(settings: Settings) -> FastAPI:
    app = create_app(settings)

    @app.get(PROBE + "/error/{code}")
    def raise_error(code: str) -> None:
        raise CASES[code]

    @app.post(PROBE + "/body")
    def accept(payload: Payload) -> Payload:
        return payload

    @app.get(PROBE + "/crash")
    def crash() -> None:
        raise RuntimeError("secret internal detail")

    return app


@pytest.fixture
def probe(settings: Settings) -> Iterator[TestClient]:
    with TestClient(_probe_app(settings), raise_server_exceptions=False) as client:
        yield client


@pytest.mark.parametrize("code", list(CASES))
def test_every_code_envelope(probe: TestClient, code: str) -> None:
    error = CASES[code]
    response = probe.get(f"{PROBE}/error/{code}")
    assert response.status_code == error.status_code
    body = response.json()["error"]
    assert body["code"] == code
    assert body["message"] == error.message
    assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert set(body) <= {"code", "message", "fields", "details", "request_id"}


def test_codes_covered() -> None:
    assert {code.value for code in ErrorCode} == set(CASES)


def test_details_and_fields(probe: TestClient) -> None:
    locked = probe.get(f"{PROBE}/error/too_many_attempts").json()["error"]
    assert locked["details"] == {"retry_after_seconds": 120}
    assert "fields" not in locked
    rejected = probe.get(f"{PROBE}/error/account_state").json()["error"]
    assert rejected["details"] == {"state": "rejected", "rejection_reason": "Not an employee"}
    invalid = probe.get(f"{PROBE}/error/validation_error").json()["error"]
    assert invalid["fields"] == {"title": "Required"}


def test_request_validation_shape(probe: TestClient) -> None:
    response = probe.post(f"{PROBE}/body", json={"count": "many"})
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert set(body["fields"]) == {"title", "count"}


def test_malformed_body_is_validation_error(probe: TestClient) -> None:
    response = probe.post(
        f"{PROBE}/body", content=b"not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unknown_route_is_not_found(probe: TestClient) -> None:
    response = probe.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_wrong_method_is_not_found(probe: TestClient) -> None:
    response = probe.delete("/health/live")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_unhandled_exception_hides_detail(probe: TestClient) -> None:
    response = probe.get(f"{PROBE}/crash", headers={REQUEST_ID_HEADER: "crash-1"})
    assert response.status_code == 500
    body = response.json()["error"]
    assert body == {"code": "server_error", "message": body["message"], "request_id": "crash-1"}
    assert "secret" not in response.text
    assert "Traceback" not in response.text
    assert response.headers[REQUEST_ID_HEADER] == "crash-1"


def test_request_id_echoed(client: TestClient) -> None:
    response = client.get("/health/live", headers={REQUEST_ID_HEADER: "abc-123"})
    assert response.headers[REQUEST_ID_HEADER] == "abc-123"


def test_request_id_generated(client: TestClient) -> None:
    first = client.get("/health/live").headers[REQUEST_ID_HEADER]
    second = client.get("/health/live").headers[REQUEST_ID_HEADER]
    assert first
    assert second
    assert first != second


def test_unsafe_request_id_replaced(client: TestClient) -> None:
    response = client.get("/health/live", headers={REQUEST_ID_HEADER: "bad id with spaces"})
    echoed = response.headers[REQUEST_ID_HEADER]
    assert echoed != "bad id with spaces"
    assert len(echoed) == 32


def test_single_request_id_header_on_error(client: TestClient) -> None:
    response = client.get("/api/v1/missing", headers={REQUEST_ID_HEADER: "one"})
    assert response.headers.get_list(REQUEST_ID_HEADER) == ["one"]
