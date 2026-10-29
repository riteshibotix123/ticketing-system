from sqlalchemy.orm import Session

from app.services.sla.scanner import SlaScanner
from app.worker import JobContext


def run(session: Session, context: JobContext) -> int:
    processed = SlaScanner(session, context.clock, context.settings.sla_time_scale).run()
    session.commit()
    return processed
