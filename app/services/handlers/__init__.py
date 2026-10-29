from app.core.events import EventBus, bus
from app.services.handlers.notification_handlers import register_notification_handlers
from app.services.handlers.sla_handlers import register_sla_handlers


def register_all(target: EventBus = bus) -> None:
    target.clear()
    register_sla_handlers(target)
    register_notification_handlers(target)
