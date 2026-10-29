from sqlalchemy import select

from app.models import Notification
from tests.factories import make_category
from tests.scenarios.helpers import Portal, hours, item_ids

TITLE = "Grievance about my manager"


def test_confidential_ticket_visibility_follows_grants(portal: Portal) -> None:
    records = make_category(
        portal.db, portal.org.departments["HR"], "Employee Records", is_confidential=True
    )
    portal.db.commit()
    number = portal.raise_ticket("asha", "HR", title=TITLE, category_id=str(records.id))
    assert portal.ticket(number).confidential

    for outsider in ("neha", "hari", "priya", "hema", "omar"):
        assert portal.get(outsider, f"/tickets/{number}").status_code == 404, outsider
    assert portal.ok(portal.get("neha", "/tickets?scope=queue"))["total"] == 0
    assert number not in item_ids(portal.ok(portal.get("priya", "/tickets?scope=all")))
    assert portal.notified(number, "ticket_created") == set()

    granted = portal.post(
        "karan",
        "/confidential-grants",
        {"user_id": str(portal.org["neha"].id), "category_id": str(records.id)},
    )
    assert granted.status_code == 200, granted.text
    assert (
        portal.post(
            "priya",
            "/confidential-grants",
            {"user_id": str(portal.org["hari"].id), "category_id": str(records.id)},
        ).status_code
        == 403
    )
    assert portal.get("neha", f"/tickets/{number}").status_code == 200
    assert item_ids(portal.ok(portal.get("neha", "/tickets?scope=queue"))) == [number]
    assert portal.get("hari", f"/tickets/{number}").status_code == 404

    portal.acknowledge("neha", number)
    texts = portal.db.scalars(
        select(Notification.text).where(Notification.ticket_id == portal.ticket(number).id)
    ).all()
    assert texts
    assert all(TITLE not in text for text in texts)
    assert all(text == f"Update on {number}" for text in texts)
    mails = portal.emails_to("asha")
    assert [mail.template for mail in mails] == ["confidential_ticket_update"]
    for mail in mails:
        assert number in mail.body_text
        assert TITLE not in mail.body_text
        assert TITLE not in mail.body_html
        assert TITLE not in mail.subject


def test_confidential_escalation_goes_only_to_people_who_can_see_it(portal: Portal) -> None:
    records = make_category(
        portal.db, portal.org.departments["HR"], "Employee Records", is_confidential=True
    )
    portal.db.commit()
    number = portal.raise_ticket("asha", "HR", title=TITLE, category_id=str(records.id))
    start = portal.clock.now()
    portal.set_time(start + hours(24))
    portal.scan()
    assert portal.notified(number, "escalation") == {"karan", "mira"}
