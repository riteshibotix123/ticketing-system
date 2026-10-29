import dataclasses
import math
import uuid
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.request_context import get_request_context
from app.core.types import JsonValue
from app.models.audit import AuditLog


def format_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def to_json_value(value: object) -> JsonValue:
    if isinstance(value, Enum):
        return to_json_value(value.value)
    if value is None or isinstance(value, bool | str | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not JSON-safe")
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return format_utc(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, BaseModel):
        return to_json_value(value.model_dump(mode="json"))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_json_value(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): to_json_value(item) for key, item in value.items()}
    if isinstance(value, set | frozenset):
        return sorted((to_json_value(item) for item in value), key=str)
    if isinstance(value, list | tuple):
        return [to_json_value(item) for item in value]
    raise TypeError(f"{type(value).__name__} is not JSON-safe")


class AuditService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    def record(
        self,
        *,
        action: str,
        object_type: str,
        object_id: str | uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        old_value: object = None,
        new_value: object = None,
        reason: str | None = None,
        detail: str | None = None,
        ticket_id: uuid.UUID | None = None,
        department_id: str | None = None,
        is_security_limited: bool = False,
        is_confidential_ticket: bool = False,
    ) -> AuditLog:
        context = get_request_context()
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            object_type=object_type,
            object_id=str(object_id) if object_id is not None else None,
            old_value=to_json_value(old_value),
            new_value=to_json_value(new_value),
            reason=reason,
            detail=detail,
            ip_address=context.ip_address if context is not None else None,
            user_agent=context.user_agent if context is not None else None,
            created_at=self._clock.now(),
            ticket_id=ticket_id,
            department_id=department_id,
            is_security_limited=is_security_limited,
            is_confidential_ticket=is_confidential_ticket,
        )
        self._session.add(entry)
        self._session.flush()
        return entry
