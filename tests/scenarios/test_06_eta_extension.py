from datetime import timedelta

from tests.scenarios.helpers import Portal, hours


def as_api_time(value: str) -> str:
    return value.replace("+00:00", "Z")


def test_eta_extension_needs_reason_and_notifies_requester(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "IT")
    portal.acknowledge("ira", number, eta_hours=6)
    start = portal.clock.now()
    later = (start + hours(8)).isoformat()
    path = f"/tickets/{number}/eta"

    assert portal.post("ira", path, {"eta": later}).status_code == 422
    revised = portal.ok(portal.post("ira", path, {"eta": later, "reason": "Parts delayed"}))
    assert revised["eta"] == as_api_time(later)
    assert portal.notified(number, "eta_changed") == {"asha"}
    assert "ticket_eta_revised" in portal.audit_actions()
    assert [email.template for email in portal.emails_to("asha")].count("eta_changed") == 1

    past = (start - hours(1)).isoformat()
    assert (
        portal.post("ira", path, {"eta": past, "reason": "Typed the wrong date"}).status_code == 422
    )


def test_overdue_eta_escalates_and_revision_ends_it(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "IT")
    portal.acknowledge("ira", number, eta_hours=6)
    start = portal.clock.now()

    portal.set_time(start + hours(4))
    portal.scan()
    assert portal.step_keys(number, "eta") == {"L1"}

    portal.set_time(start + hours(6))
    portal.scan()
    assert portal.step_keys(number, "eta") == {"L1", "L2"}
    portal.advance(timedelta(minutes=1))
    assert {"ira", "ishan", "priya"} <= portal.notified(number, "escalation")
    overdue = portal.ok(portal.get("ira", "/tickets?scope=queue&overdue_eta=true"))
    assert overdue["total"] == 1

    new_eta = (portal.clock.now() + hours(24)).isoformat()
    portal.ok(
        portal.post("ira", f"/tickets/{number}/eta", {"eta": new_eta, "reason": "New supplier"})
    )
    assert portal.ticket(number).escalation_level == 0
