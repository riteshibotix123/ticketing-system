from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import ClockDep, CurrentActor, DbSession, SettingsDep
from app.core.enums import SignupStatus
from app.core.errors import ApiError, error_response
from app.core.pagination import PageParams
from app.schemas.common import Page
from app.schemas.signup import (
    ApproveSignupBody,
    ReapplyBody,
    RejectSignupBody,
    ResendVerificationBody,
    SignupAccepted,
    SignupBody,
    SignupRequestOut,
    VerifyEmailBody,
    VerifyEmailResult,
)
from app.services.signup import SignupService

router = APIRouter(tags=["signup"])


@router.post("/auth/signup", response_model=SignupAccepted, status_code=status.HTTP_202_ACCEPTED)
def signup(
    body: SignupBody,
    request: Request,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
) -> SignupAccepted | JSONResponse:
    result = SignupService(db, clock, settings).signup(body)
    if isinstance(result, ApiError):
        return error_response(request, result)
    return result


@router.post("/auth/verify-email", response_model=VerifyEmailResult)
def verify_email(
    body: VerifyEmailBody, db: DbSession, clock: ClockDep, settings: SettingsDep
) -> VerifyEmailResult:
    state = SignupService(db, clock, settings).verify_email(body.token)
    return VerifyEmailResult(state=state)


@router.post("/auth/resend-verification", status_code=status.HTTP_202_ACCEPTED)
def resend_verification(
    body: ResendVerificationBody,
    request: Request,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
) -> Response:
    error = SignupService(db, clock, settings).resend_verification(body.email)
    if error is not None:
        return error_response(request, error)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/auth/reapply", status_code=status.HTTP_202_ACCEPTED)
def reapply(
    body: ReapplyBody,
    request: Request,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
) -> Response:
    error = SignupService(db, clock, settings).reapply(body)
    if error is not None:
        return error_response(request, error)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get(
    "/signup-requests", response_model=Page[SignupRequestOut], response_model_exclude_none=True
)
def list_signup_requests(
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
    params: Annotated[PageParams, Depends()],
    status_filter: Annotated[SignupStatus | None, Query(alias="status")] = None,
) -> Page[SignupRequestOut]:
    return SignupService(db, clock, settings).list_requests(actor, status_filter, params)


@router.post(
    "/signup-requests/{id}/approve",
    response_model=SignupRequestOut,
    response_model_exclude_none=True,
)
def approve_signup_request(
    id: str,
    body: ApproveSignupBody,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
) -> SignupRequestOut:
    return SignupService(db, clock, settings).approve(actor, id, body)


@router.post(
    "/signup-requests/{id}/reject",
    response_model=SignupRequestOut,
    response_model_exclude_none=True,
)
def reject_signup_request(
    id: str,
    body: RejectSignupBody,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
) -> SignupRequestOut:
    return SignupService(db, clock, settings).reject(actor, id, body.reason)
