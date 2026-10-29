import logging
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.core.security import create_access_token
from app.models import WorkerHeartbeat
from app.worker.main import HEARTBEAT_NAME
from tests.factories import make_department, make_user


def test_live_returns_ok(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ok(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_routes_are_outside_api_prefix(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").status_code == 404


def test_cors_allows_configured_origin_with_credentials(client: TestClient) -> None:
    response = client.options(
        "/health/live",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_rejects_unknown_origin(client: TestClient) -> None:
    response = client.options(
        "/health/live",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def beat(db: Session, at: datetime) -> None:
    db.add(WorkerHeartbeat(name=HEARTBEAT_NAME, last_seen_at=at, details={}))
    db.commit()


def test_worker_health_is_stale_without_heartbeat(client: TestClient) -> None:
    response = client.get("/health/worker")
    assert response.status_code == 503
    assert response.json() == {"status": "stale"}


def test_worker_health_ok_within_three_ticks(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings
) -> None:
    beat(db, clock.now() - timedelta(seconds=settings.worker_tick_seconds * 3))
    response = client.get("/health/worker")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_worker_health_stale_after_three_ticks(
    client: TestClient, db: Session, clock: FrozenClock, settings: Settings
) -> None:
    beat(db, clock.now() - timedelta(seconds=settings.worker_tick_seconds * 3 + 1))
    assert client.get("/health/worker").status_code == 503


def test_access_log_has_route_status_and_actor_only(
    client: TestClient,
    db: Session,
    clock: FrozenClock,
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = make_user(db, make_department(db, "IT"), email="logged@ibotix.ai")
    db.commit()
    token = create_access_token(user.id, clock.now(), settings).token
    with caplog.at_level(logging.INFO, logger="app.access"):
        client.get(
            "/api/v1/tickets/IBX-IT-2026-000001",
            headers={"Authorization": f"Bearer {token}", "X-Request-ID": "trace-1"},
        )
    records = [record for record in caplog.records if record.name == "app.access"]
    assert len(records) == 1
    record = records[0]
    assert record.__dict__["path"] == "/api/v1/tickets/{id}"
    assert record.__dict__["status_code"] == 404
    assert record.__dict__["user_id"] == str(user.id)
    assert record.__dict__["request_id"] == "trace-1"
    assert isinstance(record.__dict__["duration_ms"], int)
    formatted = JsonFormatter().format(record)
    assert "logged@ibotix.ai" not in formatted
    assert token not in formatted
    assert '"path":"/api/v1/tickets/{id}"' in formatted
