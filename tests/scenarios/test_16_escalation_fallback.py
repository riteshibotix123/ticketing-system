from app.core.enums import AccountState
from tests.scenarios.helpers import Portal, hours


def test_missing_contact_falls_back_to_admins(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "SAL")
    start = portal.clock.now()
    portal.set_time(start + hours(24))
    portal.scan()
    assert portal.notified(number, "escalation") == {"sara", "priya"}


def test_no_active_admin_falls_back_to_super_admins(portal: Portal) -> None:
    portal.org["priya"].state = AccountState.DEACTIVATED
    portal.db.commit()
    number = portal.raise_ticket("asha", "SAL")
    start = portal.clock.now()
    portal.set_time(start + hours(24))
    portal.scan()
    assert portal.notified(number, "escalation") == {"sara", "karan", "mira"}


def test_inactive_contact_is_skipped(portal: Portal) -> None:
    portal.org["ishan"].state = AccountState.DEACTIVATED
    portal.db.commit()
    number = portal.raise_ticket("asha", "IT")
    start = portal.clock.now()
    portal.set_time(start + hours(24))
    portal.scan()
    assert portal.notified(number, "escalation") == {"ira", "priya"}
