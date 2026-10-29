import logging
from collections.abc import Mapping
from enum import StrEnum
from typing import Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import REQUEST_ID_HEADER, current_request_id
from app.core.types import JsonObject, JsonValue

logger = logging.getLogger("app.errors")


class ErrorCode(StrEnum):
    UNAUTHENTICATED = "unauthenticated"
    INVALID_CREDENTIALS = "invalid_credentials"
    FORBIDDEN = "forbidden"
    ACCOUNT_STATE = "account_state"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    INVALID_TRANSITION = "invalid_transition"
    PROTECTED_ACTION_BLOCKED = "protected_action_blocked"
    TOKEN_EXPIRED = "token_expired"
    FILE_TOO_LARGE = "file_too_large"
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    VALIDATION_ERROR = "validation_error"
    TOO_MANY_ATTEMPTS = "too_many_attempts"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"


ERROR_STATUS: Final[Mapping[ErrorCode, int]] = {
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.INVALID_CREDENTIALS: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.ACCOUNT_STATE: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.INVALID_TRANSITION: 409,
    ErrorCode.PROTECTED_ACTION_BLOCKED: 409,
    ErrorCode.TOKEN_EXPIRED: 410,
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_FILE_TYPE: 415,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.TOO_MANY_ATTEMPTS: 429,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.SERVER_ERROR: 500,
}

DEFAULT_MESSAGES: Final[Mapping[ErrorCode, str]] = {
    ErrorCode.UNAUTHENTICATED: "Authentication required",
    ErrorCode.INVALID_CREDENTIALS: "Invalid email or password",
    ErrorCode.FORBIDDEN: "You are not allowed to perform this action",
    ErrorCode.ACCOUNT_STATE: "Your account is not active",
    ErrorCode.NOT_FOUND: "Not found",
    ErrorCode.CONFLICT: "The request conflicts with the current state",
    ErrorCode.INVALID_TRANSITION: "This action is not allowed in the current status",
    ErrorCode.PROTECTED_ACTION_BLOCKED: "This action requires approval by another Super Admin",
    ErrorCode.TOKEN_EXPIRED: "This link has expired",
    ErrorCode.FILE_TOO_LARGE: "The file is too large",
    ErrorCode.UNSUPPORTED_FILE_TYPE: "This file type is not allowed",
    ErrorCode.VALIDATION_ERROR: "Some fields are invalid",
    ErrorCode.TOO_MANY_ATTEMPTS: "Too many attempts, try again later",
    ErrorCode.RATE_LIMITED: "Too many requests, try again later",
    ErrorCode.SERVER_ERROR: "Something went wrong",
}

HTTP_STATUS_CODES: Final[Mapping[int, ErrorCode]] = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    410: ErrorCode.TOKEN_EXPIRED,
    413: ErrorCode.FILE_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_FILE_TYPE,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
}


class ApiError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        status_code: int | None = None,
        fields: Mapping[str, str] | None = None,
        details: JsonObject | None = None,
    ) -> None:
        self.code = code
        self.message = message if message is not None else DEFAULT_MESSAGES[code]
        self.status_code = status_code if status_code is not None else ERROR_STATUS[code]
        self.fields = dict(fields) if fields is not None else None
        self.details = details
        super().__init__(self.message)


def unauthenticated(message: str | None = None) -> ApiError:
    return ApiError(ErrorCode.UNAUTHENTICATED, message)


def invalid_credentials(message: str | None = None) -> ApiError:
    return ApiError(ErrorCode.INVALID_CREDENTIALS, message)


def forbidden(message: str | None = None) -> ApiError:
    return ApiError(ErrorCode.FORBIDDEN, message)


def account_state(state: str, rejection_reason: str | None = None) -> ApiError:
    details: JsonObject = {"state": state}
    if rejection_reason is not None:
        details["rejection_reason"] = rejection_reason
    return ApiError(ErrorCode.ACCOUNT_STATE, details=details)


def not_found(message: str | None = None) -> ApiError:
    return ApiError(ErrorCode.NOT_FOUND, message)


def conflict(message: str | None = None, details: JsonObject | None = None) -> ApiError:
    return ApiError(ErrorCode.CONFLICT, message, details=details)


def invalid_transition(message: str | None = None) -> ApiError:
    return ApiError(ErrorCode.INVALID_TRANSITION, message)


def protected_action_blocked(message: str | None = None) -> ApiError:
    return ApiError(ErrorCode.PROTECTED_ACTION_BLOCKED, message)


def token_expired(message: str | None = None) -> ApiError:
    return ApiError(ErrorCode.TOKEN_EXPIRED, message)


def file_too_large(message: str | None = None) -> ApiError:
    return ApiError(ErrorCode.FILE_TOO_LARGE, message)


def unsupported_file_type(message: str | None = None) -> ApiError:
    return ApiError(ErrorCode.UNSUPPORTED_FILE_TYPE, message)


def validation_error(fields: Mapping[str, str], message: str | None = None) -> ApiError:
    return ApiError(ErrorCode.VALIDATION_ERROR, message, fields=fields)


def too_many_attempts(retry_after_seconds: int) -> ApiError:
    return ApiError(
        ErrorCode.TOO_MANY_ATTEMPTS, details={"retry_after_seconds": retry_after_seconds}
    )


def rate_limited(retry_after_seconds: int) -> ApiError:
    return ApiError(ErrorCode.RATE_LIMITED, details={"retry_after_seconds": retry_after_seconds})


def server_error() -> ApiError:
    return ApiError(ErrorCode.SERVER_ERROR)


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    if isinstance(value, str):
        return value
    return current_request_id() or ""


def error_response(request: Request, error: ApiError) -> JSONResponse:
    request_id = _request_id(request)
    body: dict[str, JsonValue] = {"code": error.code.value, "message": error.message}
    if error.fields is not None:
        body["fields"] = dict(error.fields)
    if error.details is not None:
        body["details"] = error.details
    body["request_id"] = request_id
    return JSONResponse(
        status_code=error.status_code,
        content={"error": body},
        headers={REQUEST_ID_HEADER: request_id} if request_id else None,
    )


def _validation_fields(exc: RequestValidationError) -> dict[str, str]:
    fields: dict[str, str] = {}
    for error in exc.errors():
        location = error.get("loc", ())
        key = str(location[-1]) if location else "body"
        fields.setdefault(key, str(error.get("msg", "Invalid value")))
    return fields


async def _handle_api_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ApiError):
        return await _handle_unexpected(request, exc)
    return error_response(request, exc)


async def _handle_validation(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        return await _handle_unexpected(request, exc)
    return error_response(request, validation_error(_validation_fields(exc)))


async def _handle_http(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        return await _handle_unexpected(request, exc)
    code = HTTP_STATUS_CODES.get(exc.status_code, ErrorCode.SERVER_ERROR)
    return error_response(request, ApiError(code))


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled exception",
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"request_id": _request_id(request), "path": request.url.path},
    )
    return error_response(request, server_error())


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation)
    app.add_exception_handler(StarletteHTTPException, _handle_http)
    app.add_exception_handler(Exception, _handle_unexpected)
