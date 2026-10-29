from tests.scenarios.helpers import Portal, hours


def test_transfer_keeps_number_and_starts_a_fresh_response_clock(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "IT", title="Onboarding papers missing")
    portal.acknowledge("ira", number)
    portal.advance(hours(20))
    moved = portal.ok(
        portal.post(
            "ira",
            f"/tickets/{number}/transfer",
            {"department_id": "HR", "reason": "HR owns onboarding paperwork"},
        )
    )
    transferred_at = portal.clock.now()
    assert moved["id"] == number
    assert number.startswith("IBX-IT-")
    assert moved["department_id"] == "HR"
    assert moved["status"] == "new"
    assert moved["owner"] is None
    assert moved["sla_started_at"] == transferred_at.isoformat().replace("+00:00", "Z")
    assert {"asha", "neha", "hari"} <= portal.notified(number, "transferred")
    assert portal.get("ira", f"/tickets/{number}").status_code == 404
    assert portal.get("neha", f"/tickets/{number}").status_code == 200

    portal.set_time(transferred_at + hours(17))
    portal.scan()
    assert portal.step_keys(number, "initial_response") == set()
    portal.set_time(transferred_at + hours(18))
    portal.scan()
    assert portal.step_keys(number, "initial_response") == {"L1"}
    assert portal.notified(number, "sla_warning") == {"neha", "hari"}


def test_transfer_to_the_same_department_is_refused(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "IT")
    response = portal.post(
        "ira", f"/tickets/{number}/transfer", {"department_id": "IT", "reason": "Same place"}
    )
    assert response.status_code == 422
