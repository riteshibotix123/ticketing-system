from tests.scenarios.helpers import Portal, error_code, field, hours

SUMMARY = "Corrected the payslip record"


def work_and_resolve(portal: Portal, number: str) -> None:
    portal.ok(portal.post("neha", f"/tickets/{number}/status", {"status": "in_progress"}))
    portal.ok(portal.post("neha", f"/tickets/{number}/resolve", {"summary": SUMMARY}))


def test_summary_is_mandatory_and_confirmation_closes_with_rating(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "HR")
    portal.acknowledge("neha", number)
    portal.ok(portal.post("neha", f"/tickets/{number}/status", {"status": "in_progress"}))
    assert portal.post("neha", f"/tickets/{number}/resolve", {}).status_code == 422
    assert portal.post("neha", f"/tickets/{number}/resolve", {"summary": "done"}).status_code == 422
    resolved = portal.ok(portal.post("neha", f"/tickets/{number}/resolve", {"summary": SUMMARY}))
    assert resolved["status"] == "resolved"
    assert resolved["resolution_summary"] == SUMMARY
    assert portal.notified(number, "resolved") == {"asha"}

    assert portal.post("neha", f"/tickets/{number}/confirm-closure", {}).status_code == 403
    assert (
        portal.post("asha", f"/tickets/{number}/confirm-closure", {"rating": 6}).status_code == 422
    )
    closed = portal.ok(
        portal.post(
            "asha", f"/tickets/{number}/confirm-closure", {"rating": 5, "comment": "Thanks!"}
        )
    )
    assert closed["status"] == "closed"
    assert closed["feedback"] == {"rating": 5, "comment": "Thanks!"}


def test_reopen_count_is_limited(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "HR")
    portal.acknowledge("neha", number)
    for expected in (1, 2, 3):
        work_and_resolve(portal, number)
        portal.advance(hours(24))
        reopened = portal.ok(
            portal.post("asha", f"/tickets/{number}/reopen", {"reason": "Still wrong on payslip"})
        )
        assert reopened["status"] == "reopened"
        assert reopened["reopen_count"] == expected
        assert "neha" in portal.notified(number, "reopened")
    work_and_resolve(portal, number)
    limit = portal.post("asha", f"/tickets/{number}/reopen", {"reason": "Fourth time lucky"})
    assert limit.status_code == 409
    assert error_code(limit) == "invalid_transition"
    assert field(limit.json(), "error", "details", "max_reopens") == 3


def test_reopen_window_is_seven_days_inclusive(portal: Portal) -> None:
    inside = portal.raise_ticket("asha", "HR")
    outside = portal.raise_ticket("asha", "HR")
    for number in (inside, outside):
        portal.acknowledge("neha", number)
        work_and_resolve(portal, number)
    portal.advance(hours(24 * 7))
    on_edge = portal.post("asha", f"/tickets/{inside}/reopen", {"reason": "Came back again"})
    assert on_edge.status_code == 200
    portal.advance(hours(1))
    late = portal.post("asha", f"/tickets/{outside}/reopen", {"reason": "Came back again"})
    assert late.status_code == 409
    assert error_code(late) == "invalid_transition"
