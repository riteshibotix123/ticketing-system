from tests.scenarios.helpers import Portal, error_code, field


def assign_body(portal: Portal, who: str, reason: str | None = None) -> dict[str, str]:
    body = {"assignee_id": str(portal.org[who].id)}
    if reason is not None:
        body["reason"] = reason
    return body


def test_spoke_assigns_department_member_but_not_outsider(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "HR")
    portal.acknowledge("neha", number)

    outsider = portal.post("neha", f"/tickets/{number}/assign", assign_body(portal, "ivan"))
    assert outsider.status_code == 422
    assert error_code(outsider) == "validation_error"

    assigned = portal.ok(
        portal.post("neha", f"/tickets/{number}/assign", assign_body(portal, "harsh"))
    )
    assert assigned["status"] == "assigned"
    assert field(assigned, "assignee", "name") == "Harsh Member"
    assert "harsh" in portal.notified(number, "ticket_assigned")
    harsh_view = portal.ok(portal.get("harsh", f"/tickets/{number}"))
    allowed = harsh_view["allowed_actions"]
    assert isinstance(allowed, list)
    assert "start_work" in allowed


def test_admin_assigns_anyone_but_must_give_a_reason(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "HR")
    portal.acknowledge("neha", number)
    path = f"/tickets/{number}/assign"
    assert portal.post("priya", path, assign_body(portal, "ivan")).status_code == 422
    assert portal.post("priya", path, assign_body(portal, "ivan", "no")).status_code == 422
    assigned = portal.ok(
        portal.post("priya", path, assign_body(portal, "ivan", "IT owns the payroll tool"))
    )
    assert field(assigned, "assignee", "name") == "Ivan Member"
    assert "ticket_assigned" in portal.audit_actions()


def test_employee_cannot_assign(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "HR")
    portal.acknowledge("neha", number)
    response = portal.post("asha", f"/tickets/{number}/assign", assign_body(portal, "harsh"))
    assert response.status_code == 403
