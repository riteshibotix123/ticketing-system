from enum import StrEnum
from types import MappingProxyType
from typing import Final


class Role(StrEnum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    SPOKE = "spoke"
    EMPLOYEE = "employee"


class AccountState(StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    REJECTED = "rejected"
    DEACTIVATED = "deactivated"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketStatus(StrEnum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    AWAITING_REQUESTER = "awaiting_requester"
    ON_HOLD = "on_hold"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"
    CANCELLED = "cancelled"


class TicketAction(StrEnum):
    ACKNOWLEDGE = "acknowledge"
    ASSIGN = "assign"
    TRANSFER = "transfer"
    CHANGE_PRIORITY = "change_priority"
    REVISE_ETA = "revise_eta"
    START_WORK = "start_work"
    ASK_REQUESTER = "ask_requester"
    HOLD = "hold"
    RESUME = "resume"
    RESOLVE = "resolve"
    CONFIRM_CLOSURE = "confirm_closure"
    REOPEN = "reopen"
    CANCEL = "cancel"
    CLOSE_ADMIN = "close_admin"
    COMMENT = "comment"
    INTERNAL_NOTE = "internal_note"
    MANAGE_COLLABORATORS = "manage_collaborators"


class SlaKind(StrEnum):
    INITIAL_RESPONSE = "initial_response"
    PROGRESS_UPDATE = "progress_update"
    ETA = "eta"


class ScanStatus(StrEnum):
    PENDING = "pending"
    CLEAN = "clean"
    INFECTED = "infected"


class ProtectedActionKind(StrEnum):
    DEACTIVATE_SUPER_ADMIN = "deactivate_super_admin"
    DEMOTE_SUPER_ADMIN = "demote_super_admin"


class ProtectedActionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class SignupStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


PRIORITY_RANK: Final = MappingProxyType(
    {
        Priority.LOW: 1,
        Priority.MEDIUM: 2,
        Priority.HIGH: 3,
        Priority.CRITICAL: 4,
    }
)
