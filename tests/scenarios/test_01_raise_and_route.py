from tests.scenarios.helpers import Portal, item_ids


def test_employee_raises_hr_ticket_and_all_hr_spokes_are_notified(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "HR", title="Payslip missing for October")
    assert number.startswith("IBX-HR-2026-")
    assert portal.notified(number, "ticket_created") == {"neha", "hari"}
    for spoke in ("neha", "hari"):
        assert item_ids(portal.ok(portal.get(spoke, "/tickets?scope=queue"))) == [number]
    assert portal.ok(portal.get("ira", "/tickets?scope=queue"))["total"] == 0
    detail = portal.ok(portal.get("asha", f"/tickets/{number}"))
    assert detail["status"] == "new"
    assert detail["department_id"] == "HR"
    assert detail["owner"] is None
    assert "ticket_created" in portal.audit_actions()
