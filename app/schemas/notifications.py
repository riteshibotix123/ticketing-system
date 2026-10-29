from datetime import datetime

from app.schemas.common import ApiModel


class NotificationOut(ApiModel):
    id: str
    created_at: datetime
    read: bool
    critical: bool
    text: str
    ticket_id: str | None = None
    kind: str


class UnreadCountOut(ApiModel):
    count: int
