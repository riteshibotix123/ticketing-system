from tests.scenarios.helpers import Portal, field, hours


def test_unacknowledged_ticket_escalates_l1_l2_l3_and_ack_stops_it(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "HR")
    start = portal.clock.now()

    portal.set_time(start + hours(17))
    portal.scan()
    assert portal.step_keys(number, "initial_response") == set()

    at_l1 = portal.advance(hours(1))
    portal.scan()
    assert portal.notified(number, "sla_warning", at_l1) == {"neha", "hari"}
    assert field(portal.ok(portal.get("neha", f"/tickets/{number}")), "sla", "level") == 1

    at_l2 = start + hours(24)
    portal.set_time(at_l2)
    portal.scan()
    assert portal.notified(number, "escalation", at_l2) == {"neha", "hari", "hema", "priya"}
    assert field(portal.ok(portal.get("neha", f"/tickets/{number}")), "sla", "level") == 2

    at_l3 = start + hours(48)
    portal.set_time(at_l3)
    portal.scan()
    assert portal.notified(number, "escalation", at_l3) == {"priya", "karan", "mira"}
    assert portal.ticket(number).escalation_level == 3
    assert portal.step_keys(number, "initial_response") == {"L1", "L2", "L3"}

    portal.acknowledge("neha", number)
    portal.advance(hours(30))
    portal.scan()
    assert portal.step_keys(number, "initial_response") == {"L1", "L2", "L3"}
    assert field(portal.ok(portal.get("neha", f"/tickets/{number}")), "sla", "kind") != (
        "initial_response"
    )
