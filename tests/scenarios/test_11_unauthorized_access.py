from tests.scenarios.helpers import Portal


def strip_request_id(body: object) -> object:
    assert isinstance(body, dict)
    error = dict(body["error"])
    error.pop("request_id")
    return error


def test_another_employees_ticket_is_a_plain_404(portal: Portal) -> None:
    number = portal.raise_ticket("asha", "HR", title="Salary revision question")
    portal.ok(portal.post("asha", f"/tickets/{number}/comments", {"body": "Private details"}))

    for suffix in ("", "/timeline"):
        hidden = portal.get("omar", f"/tickets/{number}{suffix}")
        missing = portal.get("omar", f"/tickets/IBX-HR-2026-999999{suffix}")
        assert hidden.status_code == missing.status_code == 404
        assert strip_request_id(hidden.json()) == strip_request_id(missing.json())
        for leak in (number, "Salary revision", "Private details"):
            assert leak not in hidden.text

    comment = portal.post("omar", f"/tickets/{number}/comments", {"body": "Let me see"})
    assert comment.status_code == 404
    cancel = portal.post("omar", f"/tickets/{number}/cancel", {"reason": "Not mine at all"})
    assert cancel.status_code == 404
    search = portal.ok(portal.get("omar", f"/tickets?q={number}"))
    assert search["total"] == 0
    assert number not in portal.get("omar", "/notifications").text
    assert portal.get("asha", f"/tickets/{number}").status_code == 200
