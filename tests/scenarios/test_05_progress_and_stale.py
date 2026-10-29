from tests.scenarios.helpers import Portal, field, hours, item_ids


def test_update_silence_escalates_and_team_update_resets(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "HR")
    portal.acknowledge("neha", number, eta_hours=240)
    acknowledged = portal.clock.now()

    portal.set_time(acknowledged + hours(10))
    portal.ok(portal.post("neha", f"/tickets/{number}/comments", {"body": "Working on it"}))
    update = portal.clock.now()

    portal.set_time(acknowledged + hours(21))
    portal.scan()
    assert portal.step_keys(number, "progress_update") == set()
    assert not portal.ticket(number).update_overdue

    portal.set_time(update + hours(20))
    portal.scan()
    assert portal.step_keys(number, "progress_update") == {"L1"}
    assert portal.ticket(number).update_overdue
    stale = portal.ok(portal.get("neha", "/tickets?scope=queue&sla_state=stale"))
    assert item_ids(stale) == [number]

    portal.set_time(update + hours(24))
    portal.scan()
    assert portal.step_keys(number, "progress_update") == {"L1", "L2"}
    assert field(portal.ok(portal.get("neha", f"/tickets/{number}")), "sla", "level") == 2

    portal.set_time(update + hours(48))
    portal.scan()
    assert portal.step_keys(number, "progress_update") == {"L1", "L2", "L3"}
    assert portal.ticket(number).escalation_level == 3

    portal.ok(portal.post("hari", f"/tickets/{number}/comments", {"body": "Vendor replied"}))
    ticket = portal.ticket(number)
    assert ticket.escalation_level == 0
    assert not ticket.update_overdue


def test_requester_comment_is_not_a_team_update(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "HR")
    portal.acknowledge("neha", number, eta_hours=240)
    acknowledged = portal.clock.now()
    portal.set_time(acknowledged + hours(10))
    portal.ok(portal.post("asha", f"/tickets/{number}/comments", {"body": "Any news?"}))
    portal.set_time(acknowledged + hours(20))
    portal.scan()
    assert portal.step_keys(number, "progress_update") == {"L1"}
