from sqlalchemy import select

from app.models import Notification
from tests.scenarios.helpers import Portal, hours


def test_critical_ticket_alerts_contact_at_creation_and_escalates_sooner(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "IT", title="Payment gateway down", priority="critical")
    start = portal.clock.now()
    portal.scan()
    assert portal.step_keys(number, "initial_response") == {"CREATION_CONTACT"}
    assert portal.notified(number, "escalation") == {"ishan"}
    critical = portal.db.scalars(
        select(Notification.critical).where(
            Notification.ticket_id == portal.ticket(number).id,
            Notification.kind == "escalation",
        )
    ).all()
    assert critical == [True]

    portal.set_time(start + hours(11))
    portal.scan()
    assert portal.step_keys(number, "initial_response") == {"CREATION_CONTACT"}
    portal.set_time(start + hours(12))
    portal.scan()
    assert "L1" in portal.step_keys(number, "initial_response")

    portal.set_time(start + hours(30))
    portal.scan()
    assert portal.step_keys(number, "initial_response") == {"CREATION_CONTACT", "L1", "L2", "L3"}
    assert portal.ticket(number).escalation_level == 3
    before = portal.notification_count(number, "escalation")
    assert portal.scan() == 0
    assert portal.notification_count(number, "escalation") == before


def test_medium_ticket_has_no_creation_alert(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "IT")
    portal.scan()
    assert portal.step_keys(number, "initial_response") == set()
    portal.advance(hours(12))
    portal.scan()
    assert portal.step_keys(number, "initial_response") == set()


def test_raising_priority_to_critical_alerts_the_contact(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "IT")
    portal.ok(
        portal.post(
            "ira", f"/tickets/{number}/priority", {"priority": "critical", "reason": "Outage"}
        )
    )
    portal.scan()
    assert "CREATION_CONTACT" in portal.step_keys(number, "initial_response")
    assert "ishan" in portal.notified(number, "escalation")
