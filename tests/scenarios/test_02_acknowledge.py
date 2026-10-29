from tests.scenarios.helpers import Portal, field, hours


def test_spoke_acknowledges_with_eta_and_requester_sees_owner(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "HR")
    portal.advance(hours(2))
    eta = portal.clock.now() + hours(48)
    portal.ok(portal.post("neha", f"/tickets/{number}/acknowledge", {"eta": eta.isoformat()}))

    seen = portal.ok(portal.get("asha", f"/tickets/{number}"))
    assert seen["status"] == "acknowledged"
    assert field(seen, "owner", "name") == "Neha Spoke"
    assert seen["eta"] == eta.isoformat().replace("+00:00", "Z")
    assert seen["acknowledged_at"] is not None
    assert portal.notified(number, "ticket_acknowledged") == {"asha"}

    second = portal.post("hari", f"/tickets/{number}/acknowledge", {"eta": eta.isoformat()})
    assert second.status_code == 409


def test_acknowledge_needs_eta_or_reason_and_checkpoint(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "HR")
    assert portal.post("neha", f"/tickets/{number}/acknowledge", {}).status_code == 422
    checkpoint = (portal.clock.now() + hours(6)).isoformat()
    body = {"no_eta_reason": "Waiting for payroll vendor", "next_checkpoint_at": checkpoint}
    acknowledged = portal.ok(portal.post("neha", f"/tickets/{number}/acknowledge", body))
    assert acknowledged["eta"] is None
    assert acknowledged["next_checkpoint_at"] is not None
