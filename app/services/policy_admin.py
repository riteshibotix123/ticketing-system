from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.enums import Priority
from app.core.errors import forbidden, validation_error
from app.models.policy import PolicyVersion
from app.policy import Actor
from app.policy.permissions import can_manage_policy, can_read_policy
from app.schemas.policy import PolicyBody
from app.services.audit import AuditService
from app.services.policy import PolicyConfig, PolicyService

POLICY_LOCK_KEY: Final = 410_001
ALL_PRIORITIES: Final = frozenset(Priority)


def policy_errors(body: PolicyBody) -> dict[str, str]:
    errors: dict[str, str] = {}
    initial = body.initial_response_hours
    if set(body.warning_hours) != ALL_PRIORITIES:
        errors["warning_hours"] = "Give a value for every priority"
    elif any(value >= initial for value in body.warning_hours.values()):
        errors["warning_hours"] = "Every value must be below initial_response_hours"
    if set(body.l3_hours) != ALL_PRIORITIES:
        errors["l3_hours"] = "Give a value for every priority"
    elif any(value <= initial for value in body.l3_hours.values()):
        errors["l3_hours"] = "Every value must be above initial_response_hours"
    if body.update_warning_hours >= body.update_cadence_hours:
        errors["update_warning_hours"] = "Must be below update_cadence_hours"
    return errors


class PolicyAdminService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock
        self._audit = AuditService(session, clock)
        self._policy = PolicyService(session)

    def read(self, actor: Actor) -> PolicyConfig:
        if not can_read_policy(actor):
            raise forbidden()
        return self._policy.current()

    def replace(self, actor: Actor, body: PolicyBody) -> PolicyConfig:
        current = self._policy.current()
        if not can_manage_policy(actor, current.admins_can_manage_departments):
            raise forbidden()
        errors = policy_errors(body)
        if errors:
            raise validation_error(errors)
        self._session.execute(select(func.pg_advisory_xact_lock(POLICY_LOCK_KEY)))
        latest = self._policy.current_version()
        previous = PolicyConfig.model_validate(latest.config)
        config = PolicyConfig.model_validate(body.model_dump())
        stored = PolicyVersion(
            version=latest.version + 1,
            config=config.model_dump(mode="json"),
            created_by_id=actor.id,
            created_at=self._clock.now(),
        )
        self._session.add(stored)
        self._session.flush()
        self._audit.record(
            action="policy_updated",
            object_type="policy",
            object_id=str(stored.version),
            actor_id=actor.id,
            old_value=previous,
            new_value=config,
        )
        return config
