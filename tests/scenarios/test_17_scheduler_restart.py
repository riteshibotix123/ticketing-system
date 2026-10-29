from collections import Counter

from sqlalchemy import func, select

from app.models import EmailOutbox, Notification, TicketEvent, User
from tests.scenarios.helpers import Portal, hours


def escalation_counts(portal: Portal, number: str) -> Counter[str]:
    ticket = portal.ticket(number)
    rows = portal.db.scalars(
        select(User.email)
        .join(Notification, Notification.user_id == User.id)
        .where(Notification.ticket_id == ticket.id, Notification.kind == "escalation")
    ).all()
    return Counter(email.split("@", 1)[0] for email in rows)


def totals(portal: Portal) -> tuple[int, int, int]:
    def count(model: type[object]) -> int:
        value = portal.db.scalar(select(func.count()).select_from(model))
        assert isinstance(value, int)
        return value

    return count(Notification), count(EmailOutbox), count(TicketEvent)


def test_three_day_outage_catches_up_without_duplicates_or_flood(portal: Portal) -> None:
    first = portal.raise_ticket("asha", "HR", title="Outage ticket one")
    second = portal.raise_ticket("omar", "HR", title="Outage ticket two")
    critical = portal.raise_ticket("asha", "IT", title="Outage critical", priority="critical")
    start = portal.clock.now()

    portal.set_time(start + hours(72))
    assert portal.scan() == 3

    for number in (first, second):
        assert portal.step_keys(number, "initial_response") == {"L1", "L2", "L3", "L3_REPEAT_1"}
        assert portal.notified(number, "sla_warning") == {"neha", "hari"}
        assert escalation_counts(portal, number) == Counter(
            {"neha": 1, "hari": 1, "hema": 1, "priya": 2, "karan": 1, "mira": 1}
        )
        assert portal.ticket(number).escalation_level == 3
    assert portal.step_keys(critical, "initial_response") == {
        "CREATION_CONTACT",
        "L1",
        "L2",
        "L3",
        "L3_REPEAT_1",
    }
    assert escalation_counts(portal, critical)["ishan"] == 2

    snapshot = totals(portal)
    assert portal.scan() == 0
    assert totals(portal) == snapshot

    portal.run_jobs()
    while portal.run_jobs("send_outbox")["send_outbox"] > 0:
        pass
    sent = len(portal.sender.sent)
    assert sent == len(portal.db.scalars(select(EmailOutbox.id)).all())
    second_run = portal.run_jobs()
    assert second_run["sla_scan"] == 0
    assert second_run["send_outbox"] == 0
    assert len(portal.sender.sent) == sent


def test_next_repeat_is_recorded_once_after_restart(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "HR")
    start = portal.clock.now()
    portal.set_time(start + hours(72))
    portal.scan()
    portal.set_time(start + hours(96))
    portal.scan()
    portal.scan()
    keys = [key for kind, key, _ in portal.steps(number) if kind == "initial_response"]
    assert sorted(keys) == ["L1", "L2", "L3", "L3_REPEAT_1", "L3_REPEAT_2"]
