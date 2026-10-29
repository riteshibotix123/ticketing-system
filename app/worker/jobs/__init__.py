from app.worker import Job
from app.worker.jobs import (
    auto_close,
    digest,
    housekeeping,
    protected_action_expiry,
    reminders,
    send_outbox,
    sla_scan,
)


def registered_jobs() -> list[Job]:
    return [
        Job(name="sla_scan", run=sla_scan.run),
        Job(name="reminders", run=reminders.run),
        Job(name="auto_close", run=auto_close.run),
        Job(name="protected_action_expiry", run=protected_action_expiry.run),
        Job(name="housekeeping", run=housekeeping.run),
        Job(name="digest", run=digest.run),
        Job(name="send_outbox", run=send_outbox.run),
    ]
