import uuid
from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.models.preferences import DEFAULT_DIGEST_HOUR, NonCriticalEmail, NotificationPreference
from app.policy import Actor
from app.schemas.preferences import NotificationPreferencesBody, NotificationPreferencesOut


@dataclass(frozen=True, slots=True)
class EmailPreference:
    non_critical_email: NonCriticalEmail = NonCriticalEmail.IMMEDIATE
    digest_hour: int = DEFAULT_DIGEST_HOUR


def email_preference(session: Session, user_id: uuid.UUID) -> EmailPreference:
    row = session.get(NotificationPreference, user_id)
    if row is None:
        return EmailPreference()
    return EmailPreference(row.non_critical_email, row.digest_hour)


def preferences_out(preference: EmailPreference) -> NotificationPreferencesOut:
    return NotificationPreferencesOut(
        non_critical_email=preference.non_critical_email,
        digest_hour=preference.digest_hour,
        critical_email="always",
    )


class PreferenceService:
    def __init__(self, session: Session, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    def read(self, actor: Actor) -> NotificationPreferencesOut:
        return preferences_out(email_preference(self._session, actor.id))

    def replace(
        self, actor: Actor, body: NotificationPreferencesBody
    ) -> NotificationPreferencesOut:
        values = {
            "non_critical_email": body.non_critical_email,
            "digest_hour": body.digest_hour,
            "updated_at": self._clock.now(),
        }
        self._session.execute(
            insert(NotificationPreference)
            .values(user_id=actor.id, **values)
            .on_conflict_do_update(index_elements=[NotificationPreference.user_id], set_=values)
        )
        return preferences_out(EmailPreference(body.non_critical_email, body.digest_hour))
