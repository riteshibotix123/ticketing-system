import pytest

from app.core import errors
from app.core.errors import ERROR_STATUS, ApiError, ErrorCode


@pytest.mark.parametrize(
    ("error", "code", "status"),
    [
        (errors.unauthenticated(), ErrorCode.UNAUTHENTICATED, 401),
        (errors.invalid_credentials(), ErrorCode.INVALID_CREDENTIALS, 401),
        (errors.forbidden(), ErrorCode.FORBIDDEN, 403),
        (errors.account_state("pending_approval"), ErrorCode.ACCOUNT_STATE, 403),
        (errors.not_found(), ErrorCode.NOT_FOUND, 404),
        (errors.conflict(), ErrorCode.CONFLICT, 409),
        (errors.invalid_transition(), ErrorCode.INVALID_TRANSITION, 409),
        (errors.protected_action_blocked(), ErrorCode.PROTECTED_ACTION_BLOCKED, 409),
        (errors.token_expired(), ErrorCode.TOKEN_EXPIRED, 410),
        (errors.file_too_large(), ErrorCode.FILE_TOO_LARGE, 413),
        (errors.unsupported_file_type(), ErrorCode.UNSUPPORTED_FILE_TYPE, 415),
        (errors.validation_error({"title": "Required"}), ErrorCode.VALIDATION_ERROR, 422),
        (errors.too_many_attempts(30), ErrorCode.TOO_MANY_ATTEMPTS, 429),
        (errors.rate_limited(30), ErrorCode.RATE_LIMITED, 429),
        (errors.server_error(), ErrorCode.SERVER_ERROR, 500),
    ],
)
def test_helpers_set_code_and_status(error: ApiError, code: ErrorCode, status: int) -> None:
    assert error.code is code
    assert error.status_code == status
    assert error.message


def test_every_code_has_a_status() -> None:
    assert set(ERROR_STATUS) == set(ErrorCode)


def test_account_state_details() -> None:
    assert errors.account_state("deactivated").details == {"state": "deactivated"}
    assert errors.account_state("rejected", "Unknown applicant").details == {
        "state": "rejected",
        "rejection_reason": "Unknown applicant",
    }


def test_retry_after_details() -> None:
    assert errors.too_many_attempts(60).details == {"retry_after_seconds": 60}
    assert errors.rate_limited(5).details == {"retry_after_seconds": 5}


def test_validation_fields_copied() -> None:
    fields = {"title": "Required"}
    error = errors.validation_error(fields)
    fields["title"] = "changed"
    assert error.fields == {"title": "Required"}


def test_custom_message_and_status() -> None:
    error = ApiError(ErrorCode.CONFLICT, "Already approved", status_code=409)
    assert str(error) == "Already approved"
