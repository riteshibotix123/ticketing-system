from datetime import UTC, datetime, timedelta

from app.models import CloseReason
from tests.scenarios.helpers import Portal

FRIDAY_IST_10AM = datetime(2026, 10, 30, 4, 30, tzinfo=UTC)
WEDNESDAY_IST_10AM = datetime(2026, 11, 4, 4, 30, tzinfo=UTC)


def resolve_on_friday(portal: Portal) -> str:
    portal.set_time(FRIDAY_IST_10AM - timedelta(hours=2))
    number = portal.raise_ticket("asha", "HR")
    portal.acknowledge("neha", number)
    portal.ok(portal.post("neha", f"/tickets/{number}/status", {"status": "in_progress"}))
    portal.set_time(FRIDAY_IST_10AM)
    portal.ok(
        portal.post("neha", f"/tickets/{number}/resolve", {"summary": "Updated the leave record"})
    )
    return number


def test_auto_close_counts_three_business_days_across_the_weekend(portal: Portal) -> None:
    number = resolve_on_friday(portal)

    for moment in (
        datetime(2026, 11, 2, 4, 30, tzinfo=UTC),
        datetime(2026, 11, 3, 4, 30, tzinfo=UTC),
        WEDNESDAY_IST_10AM - timedelta(minutes=1),
    ):
        portal.set_time(moment)
        portal.run_jobs("auto_close")
        assert portal.ticket(number).status.value == "resolved", moment

    portal.set_time(WEDNESDAY_IST_10AM)
    assert portal.run_jobs("auto_close")["auto_close"] == 1
    ticket = portal.ticket(number)
    assert ticket.status.value == "closed"
    assert ticket.close_reason is CloseReason.AUTO
    assert ticket.closed_at == WEDNESDAY_IST_10AM
    assert "asha" in portal.notified(number, "closed")
    assert portal.run_jobs("auto_close")["auto_close"] == 0


def test_confirmation_before_the_deadline_wins(portal: Portal) -> None:
    number = resolve_on_friday(portal)
    portal.set_time(datetime(2026, 11, 2, 4, 30, tzinfo=UTC))
    portal.ok(portal.post("asha", f"/tickets/{number}/confirm-closure", {"rating": 4}))
    portal.set_time(WEDNESDAY_IST_10AM + timedelta(hours=1))
    assert portal.run_jobs("auto_close")["auto_close"] == 0
    assert portal.ticket(number).close_reason is not CloseReason.AUTO


def test_reopen_cancels_the_auto_close(portal: Portal) -> None:
    number = resolve_on_friday(portal)
    portal.set_time(datetime(2026, 11, 3, 4, 30, tzinfo=UTC))
    portal.ok(portal.post("asha", f"/tickets/{number}/reopen", {"reason": "Balance still wrong"}))
    portal.set_time(WEDNESDAY_IST_10AM + timedelta(hours=1))
    portal.run_jobs("auto_close")
    assert portal.ticket(number).status.value == "reopened"
