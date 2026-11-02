from app.services.sla import scanner
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
        Job(name="sla_scan", run=sla_scan.run, batch_size=scanner.BATCH_SIZE),
        Job(name="reminders", run=reminders.run, batch_size=reminders.BATCH_SIZE),
        Job(name="auto_close", run=auto_close.run, batch_size=auto_close.BATCH_SIZE),
        Job(
            name="protected_action_expiry",
            run=protected_action_expiry.run,
            batch_size=protected_action_expiry.BATCH_SIZE,
        ),
        Job(name="housekeeping", run=housekeeping.run, batch_size=housekeeping.BATCH_SIZE),
        Job(name="digest", run=digest.run, batch_size=digest.BATCH_SIZE),
        Job(name="send_outbox", run=send_outbox.run, batch_size=send_outbox.BATCH_SIZE),
    ]
