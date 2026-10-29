import logging
import re
import time
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
MAX_USER_AGENT_LENGTH = 512

access_logger = logging.getLogger("app.access")


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str
    ip_address: str | None
    user_agent: str | None


_current: ContextVar[RequestContext | None] = ContextVar("request_context", default=None)


def get_request_context() -> RequestContext | None:
    return _current.get()


def current_request_id() -> str | None:
    context = _current.get()
    return context.request_id if context is not None else None


def set_request_context(context: RequestContext) -> Token[RequestContext | None]:
    return _current.set(context)


def reset_request_context(token: Token[RequestContext | None]) -> None:
    _current.reset(token)


def resolve_request_id(value: str | None) -> str:
    if value is not None and REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return uuid.uuid4().hex


def build_context(scope: Scope) -> RequestContext:
    headers = Headers(scope=scope)
    client = scope.get("client")
    user_agent = headers.get("user-agent")
    return RequestContext(
        request_id=resolve_request_id(headers.get(REQUEST_ID_HEADER)),
        ip_address=client[0] if client else None,
        user_agent=user_agent[:MAX_USER_AGENT_LENGTH] if user_agent else None,
    )


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        context = build_context(scope)
        state = scope.setdefault("state", {})
        state["request_id"] = context.request_id
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = MutableHeaders(scope=message)
                if REQUEST_ID_HEADER not in headers:
                    headers.append(REQUEST_ID_HEADER, context.request_id)
            await send(message)

        token = set_request_context(context)
        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            log_request(scope, state, context, status_code, started)
            reset_request_context(token)


def route_template(scope: Scope) -> str:
    if scope.get("route") is None:
        return "unmatched"
    params = scope.get("path_params") or {}
    names = {str(value): str(name) for name, value in params.items()}
    segments = str(scope.get("path", "")).split("/")
    return "/".join(f"{{{names[part]}}}" if part in names else part for part in segments)


def log_request(
    scope: Scope,
    state: dict[str, object],
    context: RequestContext,
    status_code: int,
    started: float,
) -> None:
    user_id = state.get("user_id")
    access_logger.info(
        "request completed",
        extra={
            "request_id": context.request_id,
            "method": str(scope.get("method", "")),
            "path": route_template(scope),
            "status_code": status_code,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "user_id": user_id if isinstance(user_id, str) else None,
        },
    )
