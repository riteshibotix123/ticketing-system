import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import IST, Clock, to_ist
from app.core.errors import ApiError, conflict, forbidden, not_found, validation_error
from app.core.types import JsonObject
from app.models.identity import User
from app.models.saved_view import SavedView
from app.policy import Actor
from app.policy.reports import built_in_view_scope, owns_saved_view, sees_department_views
from app.queries.tickets import SORTS
from app.schemas.saved_views import (
    SavedViewCreate,
    SavedViewOut,
    SavedViewUpdate,
    TicketListQueryModel,
)
from app.services.audit import format_utc
from app.services.policy import PolicyService
from app.services.ticket_reads import parse_statuses, parse_uuid

BUILT_IN_PREFIX: Final = "builtin."
MAX_VIEWS_PER_USER: Final = 50
AWAITING_LONGER_THAN: Final = timedelta(hours=48)
ID_FIELDS: Final = ("category_id", "requester_id", "assignee_id")
TIME_FIELDS: Final = ("awaiting_before", "created_from", "created_to")


@dataclass(frozen=True, slots=True)
class BuiltInView:
    key: str
    name: str
    spokes_only: bool
    query: Callable[[str, datetime], JsonObject]


def _start_of_ist_day(now: datetime) -> str:
    local = to_ist(now)
    return format_utc(datetime(local.year, local.month, local.day, tzinfo=IST))


BUILT_IN_VIEWS: Final = (
    BuiltInView(
        "department_breached",
        "My Department - SLA Breached",
        True,
        lambda _scope, _now: {"scope": "queue", "sla_state": "breached"},
    ),
    BuiltInView(
        "no_update_24h",
        "No Update > 24h",
        False,
        lambda scope, _now: {"scope": scope, "sla_state": "stale"},
    ),
    BuiltInView(
        "unassigned_today",
        "Unassigned Today",
        False,
        lambda scope, now: {
            "scope": scope,
            "unassigned": True,
            "created_from": _start_of_ist_day(now),
        },
    ),
    BuiltInView(
        "escalated_l3",
        "Escalated L3",
        False,
        lambda scope, _now: {"scope": scope, "escalation_level": 3},
    ),
    BuiltInView(
        "awaiting_requester_48h",
        "Awaiting Requester > 48h",
        False,
        lambda scope, now: {
            "scope": scope,
            "awaiting_before": format_utc(now - AWAITING_LONGER_THAN),
        },
    ),
)
BUILT_IN_KEYS: Final = frozenset(view.key for view in BUILT_IN_VIEWS)


def normalize_query(raw: JsonObject) -> JsonObject:
    try:
        model = TicketListQueryModel.model_validate(raw)
    except ValidationError as exc:
        fields: dict[str, str] = {}
        for error in exc.errors():
            location = error.get("loc", ())
            key = str(location[0]) if location else "query"
            fields.setdefault(f"query.{key}", str(error.get("msg", "Invalid value")))
        raise validation_error(fields) from exc
    try:
        parse_statuses(model.status or [])
    except ApiError as exc:
        raise validation_error({"query.status": "Unknown status"}) from exc
    for field in ID_FIELDS:
        try:
            parse_uuid(getattr(model, field), field)
        except ApiError as exc:
            raise validation_error({f"query.{field}": "Must be a valid id"}) from exc
    if model.sort is not None and model.sort.strip() not in SORTS:
        raise validation_error({"query.sort": f"Must be one of: {', '.join(sorted(SORTS))}"})
    normalized = model.model_dump(mode="json", exclude_none=True)
    for field in TIME_FIELDS:
        value = getattr(model, field)
        if isinstance(value, datetime):
            normalized[field] = format_utc(value)
    return normalized


def view_out(view: SavedView) -> SavedViewOut:
    return SavedViewOut(
        id=str(view.id),
        name=view.name,
        built_in=False,
        query=view.query,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


class SavedViewService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    def list_views(self, actor: Actor) -> list[SavedViewOut]:
        own = self._session.scalars(
            select(SavedView)
            .where(SavedView.owner_id == actor.id, SavedView.deleted_at.is_(None))
            .order_by(func.lower(SavedView.name), SavedView.id)
        )
        return [*self._built_ins(actor), *(view_out(view) for view in own)]

    def create(self, actor: Actor, body: SavedViewCreate) -> SavedViewOut:
        query = normalize_query(body.query)
        self._lock_owner(actor)
        active = self._session.scalar(
            select(func.count())
            .select_from(SavedView)
            .where(SavedView.owner_id == actor.id, SavedView.deleted_at.is_(None))
        )
        if (active or 0) >= MAX_VIEWS_PER_USER:
            raise conflict(f"You can keep at most {MAX_VIEWS_PER_USER} saved views")
        self._ensure_unique(actor, body.name, None)
        now = self._clock.now()
        view = SavedView(
            owner_id=actor.id, name=body.name, query=query, created_at=now, updated_at=now
        )
        self._session.add(view)
        self._session.flush()
        return view_out(view)

    def update(self, actor: Actor, view_id: str, body: SavedViewUpdate) -> SavedViewOut:
        query = normalize_query(body.query) if body.query is not None else None
        self._lock_owner(actor)
        view = self._own(actor, view_id)
        if body.name is not None:
            self._ensure_unique(actor, body.name, view.id)
            view.name = body.name
        if query is not None:
            view.query = query
        view.updated_at = self._clock.now()
        self._session.flush()
        return view_out(view)

    def delete(self, actor: Actor, view_id: str) -> None:
        view = self._own(actor, view_id)
        now = self._clock.now()
        view.deleted_at = now
        view.updated_at = now
        self._session.flush()

    def _built_ins(self, actor: Actor) -> list[SavedViewOut]:
        policy = PolicyService(self._session).current()
        scope = built_in_view_scope(actor, policy.admins_can_manage_departments)
        now = self._clock.now()
        return [
            SavedViewOut(
                id=f"{BUILT_IN_PREFIX}{view.key}",
                name=view.name,
                built_in=True,
                query=view.query(scope, now),
                created_at=None,
                updated_at=None,
            )
            for view in BUILT_IN_VIEWS
            if not view.spokes_only or sees_department_views(actor)
        ]

    def _own(self, actor: Actor, view_id: str) -> SavedView:
        key = view_id.strip()
        if key.startswith(BUILT_IN_PREFIX) and key.removeprefix(BUILT_IN_PREFIX) in BUILT_IN_KEYS:
            raise forbidden()
        try:
            identifier = uuid.UUID(key)
        except ValueError as exc:
            raise not_found() from exc
        view = self._session.scalars(
            select(SavedView)
            .where(SavedView.id == identifier, SavedView.deleted_at.is_(None))
            .with_for_update()
        ).first()
        if view is None or not owns_saved_view(actor, view.owner_id):
            raise not_found()
        return view

    def _ensure_unique(self, actor: Actor, name: str, exclude: uuid.UUID | None) -> None:
        statement = select(SavedView.id).where(
            SavedView.owner_id == actor.id,
            SavedView.deleted_at.is_(None),
            func.lower(SavedView.name) == name.lower(),
        )
        if exclude is not None:
            statement = statement.where(SavedView.id != exclude)
        if self._session.scalars(statement).first() is not None:
            raise conflict("You already have a saved view with this name")

    def _lock_owner(self, actor: Actor) -> None:
        self._session.execute(select(User.id).where(User.id == actor.id).with_for_update())
