from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.integrations.email import EmailSender


@dataclass(frozen=True)
class JobContext:
    clock: Clock
    settings: Settings
    sender: EmailSender


@dataclass(frozen=True)
class Job:
    name: str
    run: Callable[[Session, JobContext], int]
