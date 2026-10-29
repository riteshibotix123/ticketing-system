import pytest
from jinja2 import UndefinedError

from app.core.types import JsonObject
from app.services.email_templates import SUBJECTS, UnknownEmailTemplateError, render_email

BASE = "https://helpdesk.ibotix.ai"

CASES: list[tuple[str, JsonObject, list[str]]] = [
    (
        "verify_email",
        {"name": "Asha", "token": "tok-123", "expires_hours": 24},
        [f"{BASE}/verify-email?token=tok-123", "24 hours"],
    ),
    (
        "account_exists_notice",
        {"name": "Asha"},
        [f"{BASE}/login", f"{BASE}/forgot-password"],
    ),
    ("signup_approved", {"name": "Asha"}, [f"{BASE}/login"]),
    ("signup_rejected", {"name": "Asha", "reason": "Wrong department"}, ["Wrong department"]),
    (
        "password_reset",
        {"name": "Asha", "token": "tok-456", "expires_minutes": 60},
        [f"{BASE}/reset-password?token=tok-456", "60 minutes"],
    ),
]


def test_every_template_has_a_case() -> None:
    assert {name for name, _, _ in CASES} == set(SUBJECTS)


@pytest.mark.parametrize(("template", "context", "expected"), CASES)
def test_renders_subject_text_and_html(
    template: str, context: JsonObject, expected: list[str]
) -> None:
    rendered = render_email(template, {**context, "frontend_base_url": BASE})

    assert rendered.subject == SUBJECTS[template]
    assert "Hello Asha," in rendered.body_text
    assert "<p>Hello Asha,</p>" in rendered.body_html
    for fragment in expected:
        assert fragment in rendered.body_text
        assert fragment in rendered.body_html


def test_html_escapes_values_and_text_does_not() -> None:
    rendered = render_email(
        "signup_approved", {"name": "<b>Ann & Co</b>", "frontend_base_url": BASE}
    )

    assert "&lt;b&gt;Ann &amp; Co&lt;/b&gt;" in rendered.body_html
    assert "<b>Ann" not in rendered.body_html
    assert "<b>Ann & Co</b>" in rendered.body_text


def test_token_is_url_encoded() -> None:
    rendered = render_email(
        "password_reset",
        {"name": "Asha", "token": "a b&c", "expires_minutes": 60, "frontend_base_url": BASE},
    )

    assert "token=a%20b%26c" in rendered.body_text
    assert "token=a%20b%26c" in rendered.body_html


def test_rejection_without_reason_omits_reason_line() -> None:
    rendered = render_email(
        "signup_rejected", {"name": "Asha", "reason": None, "frontend_base_url": BASE}
    )

    assert "Reason" not in rendered.body_text
    assert "Reason" not in rendered.body_html
    assert f"{BASE}/login" in rendered.body_text


def test_missing_context_value_raises() -> None:
    with pytest.raises(UndefinedError):
        render_email("verify_email", {"name": "Asha", "frontend_base_url": BASE})


def test_unknown_template_raises() -> None:
    with pytest.raises(UnknownEmailTemplateError):
        render_email("ticket_title_dump", {"frontend_base_url": BASE})
