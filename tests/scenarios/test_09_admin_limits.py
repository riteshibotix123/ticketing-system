from tests.factories import make_category
from tests.scenarios.helpers import Portal, item_ids


def test_admin_sees_every_non_confidential_ticket(portal: Portal) -> None:
    hr = portal.raise_ticket("asha", "HR")
    it = portal.raise_ticket("omar", "IT")
    secret = make_category(portal.db, portal.org.departments["HR"], "Records", is_confidential=True)
    portal.db.commit()
    hidden = portal.raise_ticket("asha", "HR", category_id=str(secret.id))

    listed = item_ids(portal.ok(portal.get("priya", "/tickets?scope=all&page_size=100")))
    assert set(listed) == {hr, it}
    assert portal.get("priya", f"/tickets/{hr}").status_code == 200
    assert portal.get("priya", f"/tickets/{it}").status_code == 200
    assert portal.get("priya", f"/tickets/{hidden}").status_code == 404
    karan = item_ids(portal.ok(portal.get("karan", "/tickets?scope=all&page_size=100")))
    assert set(karan) == {hr, it, hidden}


def test_admin_cannot_manage_admins(portal: Portal) -> None:
    assert portal.get("priya", "/admins").status_code == 403
    promote = portal.post("priya", "/admins", {"user_id": str(portal.org["omar"].id)})
    assert promote.status_code == 403
    assert portal.delete("priya", f"/admins/{portal.org['priya'].id}").status_code == 403
    assert portal.get("priya", "/protected-actions").status_code == 403
    assert portal.get("priya", "/confidential-grants").status_code == 403
    assert portal.get("karan", "/admins").status_code == 200


def test_employee_cannot_list_all_tickets(portal: Portal) -> None:
    portal.raise_ticket("asha", "HR")
    assert portal.get("omar", "/tickets?scope=all").status_code == 403
    assert portal.ok(portal.get("omar", "/tickets"))["total"] == 0
