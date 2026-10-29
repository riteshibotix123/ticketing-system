from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import ClockDep, CurrentActor, DbSession, SettingsDep, require_allowed_origin
from app.core.config import Settings
from app.core.errors import ApiError, error_response
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginSuccess,
    Me,
    MfaCodeRequest,
    MfaConfirmSuccess,
    MfaEnrolRequired,
    MfaRequired,
    MfaSetupResponse,
    MfaTokenRequest,
    RefreshResponse,
    ResetPasswordRequest,
)
from app.services.auth import AuthService
from app.services.me import MeService

REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"

router = APIRouter(prefix="/auth", tags=["auth"])

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_days * 86400,
        path=REFRESH_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


@router.post("/login", response_model=LoginSuccess | MfaRequired | MfaEnrolRequired)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
) -> LoginSuccess | MfaRequired | MfaEnrolRequired | JSONResponse:
    result = AuthService(db, clock, settings).login(body.email, body.password)
    if isinstance(result, ApiError):
        return error_response(request, result)
    if isinstance(result, MfaRequired | MfaEnrolRequired):
        return result
    _set_refresh_cookie(response, result.refresh_token, settings)
    return result.body


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(
    body: MfaTokenRequest, db: DbSession, clock: ClockDep, settings: SettingsDep
) -> MfaSetupResponse:
    return AuthService(db, clock, settings).mfa_setup(body.mfa_token)


@router.post("/mfa/confirm", response_model=MfaConfirmSuccess)
def mfa_confirm(
    body: MfaCodeRequest,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
) -> MfaConfirmSuccess:
    result = AuthService(db, clock, settings).mfa_confirm(body.mfa_token, body.code)
    _set_refresh_cookie(response, result.refresh_token, settings)
    return result.body


@router.post("/mfa/verify", response_model=LoginSuccess)
def mfa_verify(
    body: MfaCodeRequest,
    request: Request,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
) -> LoginSuccess | JSONResponse:
    result = AuthService(db, clock, settings).mfa_verify(body.mfa_token, body.code)
    if isinstance(result, ApiError):
        return error_response(request, result)
    _set_refresh_cookie(response, result.refresh_token, settings)
    return result.body


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    dependencies=[Depends(require_allowed_origin)],
)
def refresh(
    request: Request,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
    refresh_token: RefreshCookie = None,
) -> RefreshResponse | JSONResponse:
    result = AuthService(db, clock, settings).refresh(refresh_token)
    if isinstance(result, ApiError):
        return error_response(request, result)
    _set_refresh_cookie(response, result.refresh_token, settings)
    return result.body


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_allowed_origin)],
)
def logout(
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
    refresh_token: RefreshCookie = None,
) -> Response:
    AuthService(db, clock, settings).logout(refresh_token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response, settings)
    return response


@router.get("/me", response_model=Me)
def me(actor: CurrentActor, db: DbSession) -> Me:
    return MeService(db).me(actor)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
) -> Response:
    error = AuthService(db, clock, settings).forgot_password(body.email)
    if error is not None:
        return error_response(request, error)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    body: ResetPasswordRequest,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
) -> Response:
    AuthService(db, clock, settings).reset_password(body.token, body.password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
