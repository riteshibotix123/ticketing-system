import hashlib
import itertools
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.enums import (
    AccountState,
    Priority,
    ProtectedActionKind,
    ProtectedActionStatus,
    Role,
    ScanStatus,
    SignupStatus,
    TicketStatus,
)
from app.core.ids import format_ticket_no
from app.core.types import JsonObject
from app.models import (
    Attachment,
    Category,
    CloseReason,
    ConfidentialGrant,
    Department,
    EmailOutbox,
    EmailToken,
    EmailTokenPurpose,
    EscalationEvent,
    Notification,
    PolicyVersion,
    ProtectedActionRequest,
    RateLimitHit,
    RefreshToken,
    SignupRequest,
    SlaTimer,
    SpokeAssignment,
    Ticket,
    TicketCollaborator,
    TicketCounter,
    TicketEvent,
    TicketEventKind,
    TimerKind,
    User,
)

FACTORY_NOW = datetime(2026, 10, 27, 4, 30, tzinfo=UTC)
PLACEHOLDER_PASSWORD_HASH = "factory-placeholder-hash"

_sequence = itertools.count(1)


def _next() -> int:
    return next(_sequence)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _persist[T](db: Session, instance: T) -> T:
    db.add(instance)
    db.flush()
    return instance


def make_department(
    db: Session,
    code: str = "IT",
    name: str | None = None,
    *,
    is_active: bool = True,
    escalation_contact: User | None = None,
    at: datetime = FACTORY_NOW,
) -> Department:
    return _persist(
        db,
        Department(
            id=code,
            name=name if name is not None else f"{code} Department",
            is_active=is_active,
            escalation_contact_user_id=escalation_contact.id if escalation_contact else None,
            created_at=at,
            updated_at=at,
        ),
    )


def make_user(
    db: Session,
    department: Department,
    *,
    email: str | None = None,
    name: str | None = None,
    title: str | None = None,
    role: Role = Role.EMPLOYEE,
    state: AccountState = AccountState.ACTIVE,
    password_hash: str = PLACEHOLDER_PASSWORD_HASH,
    at: datetime = FACTORY_NOW,
) -> User:
    number = _next()
    active = state is AccountState.ACTIVE
    return _persist(
        db,
        User(
            email=email if email is not None else f"user{number}@ibotix.ai",
            name=name if name is not None else f"User {number}",
            title=title,
            password_hash=password_hash,
            home_department_id=department.id,
            global_role=role,
            state=state,
            email_verified_at=at if state is not AccountState.PENDING_VERIFICATION else None,
            approved_at=at if active else None,
            created_at=at,
            updated_at=at,
        ),
    )


def make_category(
    db: Session,
    department: Department,
    name: str | None = None,
    *,
    is_confidential: bool = False,
    is_active: bool = True,
    at: datetime = FACTORY_NOW,
) -> Category:
    return _persist(
        db,
        Category(
            department_id=department.id,
            name=name if name is not None else f"Category {_next()}",
            is_confidential=is_confidential,
            is_active=is_active,
            created_at=at,
            updated_at=at,
        ),
    )


def make_spoke_assignment(
    db: Session,
    user: User,
    department: Department,
    *,
    granted_by: User | None = None,
    revoked_at: datetime | None = None,
    at: datetime = FACTORY_NOW,
) -> SpokeAssignment:
    return _persist(
        db,
        SpokeAssignment(
            user_id=user.id,
            department_id=department.id,
            granted_by_id=granted_by.id if granted_by else None,
            granted_at=at,
            revoked_at=revoked_at,
        ),
    )


def make_confidential_grant(
    db: Session,
    user: User,
    category: Category,
    *,
    granted_by: User | None = None,
    revoked_at: datetime | None = None,
    at: datetime = FACTORY_NOW,
) -> ConfidentialGrant:
    return _persist(
        db,
        ConfidentialGrant(
            user_id=user.id,
            category_id=category.id,
            granted_by_id=granted_by.id if granted_by else None,
            granted_at=at,
            revoked_at=revoked_at,
        ),
    )


def make_signup_request(
    db: Session,
    user: User,
    department: Department,
    *,
    requested_role: Role = Role.EMPLOYEE,
    status: SignupStatus = SignupStatus.PENDING,
    at: datetime = FACTORY_NOW,
) -> SignupRequest:
    return _persist(
        db,
        SignupRequest(
            user_id=user.id,
            requested_role=requested_role,
            requested_department_id=department.id,
            status=status,
            created_at=at,
            updated_at=at,
        ),
    )


def make_email_token(
    db: Session,
    user: User,
    *,
    purpose: EmailTokenPurpose = EmailTokenPurpose.VERIFY,
    raw_token: str | None = None,
    lifetime: timedelta = timedelta(hours=24),
    at: datetime = FACTORY_NOW,
) -> EmailToken:
    token = raw_token if raw_token is not None else f"email-token-{_next()}"
    return _persist(
        db,
        EmailToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=_hash(token),
            expires_at=at + lifetime,
            created_at=at,
            updated_at=at,
        ),
    )


def make_refresh_token(
    db: Session,
    user: User,
    *,
    family_id: uuid.UUID | None = None,
    raw_token: str | None = None,
    lifetime: timedelta = timedelta(days=7),
    at: datetime = FACTORY_NOW,
) -> RefreshToken:
    token = raw_token if raw_token is not None else f"refresh-token-{_next()}"
    return _persist(
        db,
        RefreshToken(
            user_id=user.id,
            family_id=family_id if family_id is not None else uuid.uuid4(),
            token_hash=_hash(token),
            expires_at=at + lifetime,
            created_at=at,
            updated_at=at,
        ),
    )


def make_protected_action(
    db: Session,
    target: User,
    requested_by: User,
    *,
    kind: ProtectedActionKind = ProtectedActionKind.DEACTIVATE_SUPER_ADMIN,
    status: ProtectedActionStatus = ProtectedActionStatus.PENDING,
    reason: str = "Leaving the company",
    at: datetime = FACTORY_NOW,
) -> ProtectedActionRequest:
    return _persist(
        db,
        ProtectedActionRequest(
            kind=kind,
            target_user_id=target.id,
            requested_by_id=requested_by.id,
            status=status,
            reason=reason,
            expires_at=at + timedelta(hours=72),
            created_at=at,
            updated_at=at,
        ),
    )


def make_rate_limit_hit(
    db: Session,
    key: str,
    *,
    window_start: datetime = FACTORY_NOW,
    count: int = 1,
) -> RateLimitHit:
    return _persist(db, RateLimitHit(key=key, window_start=window_start, count=count))


def make_policy_version(
    db: Session,
    version: int,
    config: JsonObject,
    *,
    created_by: User | None = None,
    at: datetime = FACTORY_NOW,
) -> PolicyVersion:
    return _persist(
        db,
        PolicyVersion(
            version=version,
            config=dict(config),
            created_by_id=created_by.id if created_by else None,
            created_at=at,
        ),
    )


OWNED_STATUSES = frozenset(TicketStatus) - {TicketStatus.NEW, TicketStatus.CANCELLED}
ASSIGNED_STATUSES = OWNED_STATUSES - {TicketStatus.ACKNOWLEDGED}


def make_ticket(
    db: Session,
    requester: User,
    department: Department,
    *,
    status: TicketStatus = TicketStatus.NEW,
    priority: Priority = Priority.MEDIUM,
    category: Category | None = None,
    confidential: bool = False,
    title: str | None = None,
    owner: User | None = None,
    assignee: User | None = None,
    ticket_no: str | None = None,
    eta: datetime | None = None,
    escalation_level: int = 0,
    update_overdue: bool = False,
    at: datetime = FACTORY_NOW,
) -> Ticket:
    number = _next()
    if owner is None and status in OWNED_STATUSES:
        owner = make_user(db, department)
    if assignee is None and status in ASSIGNED_STATUSES:
        assignee = owner
    ticket = Ticket(
        ticket_no=ticket_no
        if ticket_no is not None
        else format_ticket_no(department.id, at.year, number),
        origin_department_code=department.id,
        department_id=department.id,
        category_id=category.id if category else None,
        title=title if title is not None else f"Ticket {number}",
        description=f"Description of ticket {number}",
        requested_priority=priority,
        priority=priority,
        confidential=confidential or bool(category and category.is_confidential),
        status=status,
        requester_id=requester.id,
        owner_id=owner.id if owner else None,
        assignee_id=assignee.id if assignee else None,
        sla_started_at=at,
        escalation_level=escalation_level,
        update_overdue=update_overdue,
        created_at=at,
        updated_at=at,
    )
    if owner is not None:
        ticket.acknowledged_at = at + timedelta(hours=1)
        ticket.eta = at + timedelta(days=2)
        ticket.last_team_update_at = ticket.acknowledged_at
    if eta is not None:
        ticket.eta = eta
    if status is TicketStatus.AWAITING_REQUESTER:
        ticket.awaiting_since = at + timedelta(hours=2)
    if status is TicketStatus.ON_HOLD:
        ticket.hold_reason = "Waiting for vendor"
        ticket.hold_review_date = at + timedelta(days=3)
    if status in {TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.REOPENED}:
        ticket.resolution_summary = "Fixed"
        ticket.resolved_at = at + timedelta(hours=4)
    if status is TicketStatus.CLOSED:
        ticket.closed_at = at + timedelta(hours=5)
        ticket.close_reason = CloseReason.CONFIRMED
    if status is TicketStatus.REOPENED:
        ticket.reopen_count = 1
    if status is TicketStatus.CANCELLED:
        ticket.cancel_reason = "No longer needed"
    return _persist(db, ticket)


def make_ticket_counter(
    db: Session, department_code: str, year: int = 2026, last_value: int = 0
) -> TicketCounter:
    return _persist(
        db, TicketCounter(department_code=department_code, year=year, last_value=last_value)
    )


def make_collaborator(
    db: Session,
    ticket: Ticket,
    user: User,
    *,
    added_by: User | None = None,
    at: datetime = FACTORY_NOW,
) -> TicketCollaborator:
    return _persist(
        db,
        TicketCollaborator(
            ticket_id=ticket.id,
            user_id=user.id,
            added_by_id=added_by.id if added_by else None,
            added_at=at,
        ),
    )


def make_ticket_event(
    db: Session,
    ticket: Ticket,
    *,
    actor: User | None = None,
    kind: TicketEventKind = TicketEventKind.AUDIT,
    action: str | None = "ticket.created",
    body: str | None = None,
    is_public: bool = True,
    at: datetime = FACTORY_NOW,
) -> TicketEvent:
    return _persist(
        db,
        TicketEvent(
            ticket_id=ticket.id,
            at=at,
            actor_id=actor.id if actor else None,
            kind=kind,
            action=action,
            body=body,
            is_public=is_public,
        ),
    )


def make_attachment(
    db: Session,
    uploader: User,
    *,
    ticket: Ticket | None = None,
    scan_status: ScanStatus = ScanStatus.CLEAN,
    at: datetime = FACTORY_NOW,
) -> Attachment:
    number = _next()
    return _persist(
        db,
        Attachment(
            ticket_id=ticket.id if ticket else None,
            uploader_id=uploader.id,
            file_name=f"file{number}.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            storage_key=f"attachments/{uuid.uuid4()}",
            sha256=_hash(f"file{number}"),
            scan_status=scan_status,
            created_at=at,
        ),
    )


def make_timer(
    db: Session,
    ticket: Ticket,
    kind: TimerKind = TimerKind.INITIAL_RESPONSE,
    *,
    cycle: int = 1,
    started_at: datetime = FACTORY_NOW,
    due_in: timedelta = timedelta(hours=24),
) -> SlaTimer:
    return _persist(
        db,
        SlaTimer(
            ticket_id=ticket.id,
            kind=kind,
            cycle=cycle,
            started_at=started_at,
            warning_at=started_at + due_in * 0.75,
            due_at=started_at + due_in,
            l3_at=started_at + due_in * 2,
        ),
    )


def make_escalation_event(
    db: Session,
    ticket: Ticket,
    *,
    timer_kind: TimerKind = TimerKind.INITIAL_RESPONSE,
    cycle: int = 1,
    level: int = 2,
    step_key: str = "L2",
    recipients: list[User] | None = None,
    at: datetime = FACTORY_NOW,
) -> EscalationEvent:
    return _persist(
        db,
        EscalationEvent(
            ticket_id=ticket.id,
            timer_kind=timer_kind,
            cycle=cycle,
            level=level,
            step_key=step_key,
            at=at,
            recipient_ids=[user.id for user in recipients or []],
        ),
    )


def make_notification(
    db: Session,
    user: User,
    *,
    ticket: Ticket | None = None,
    kind: str = "ticket_created",
    text: str = "New ticket",
    critical: bool = False,
    dedupe_key: str | None = None,
    read_at: datetime | None = None,
    at: datetime = FACTORY_NOW,
) -> Notification:
    return _persist(
        db,
        Notification(
            user_id=user.id,
            ticket_id=ticket.id if ticket else None,
            kind=kind,
            text=text,
            critical=critical,
            dedupe_key=dedupe_key,
            created_at=at,
            read_at=read_at,
        ),
    )


def make_outbox_email(
    db: Session,
    to_address: str,
    *,
    notification: Notification | None = None,
    template: str = "verify_email",
    at: datetime = FACTORY_NOW,
) -> EmailOutbox:
    return _persist(
        db,
        EmailOutbox(
            notification_id=notification.id if notification else None,
            to_address=to_address,
            template=template,
            context={},
            subject="Subject",
            body_text="Body",
            body_html="<p>Body</p>",
            next_attempt_at=at,
            created_at=at,
        ),
    )


@dataclass(frozen=True)
class TicketWorld:
    it: Department
    hr: Department
    users: dict[str, User]
    tickets: dict[str, Ticket]
    normal_category: Category
    secret_category: Category


WORLD_ACTORS = (
    "requester",
    "assignee",
    "collaborator",
    "spoke",
    "spoke_with_grant",
    "other_spoke",
    "admin",
    "admin_with_grant",
    "super_admin",
    "employee_with_grant",
    "unrelated",
)


def make_ticket_world(db: Session) -> TicketWorld:
    it = make_department(db, "IT")
    hr = make_department(db, "HR")
    roles = {"admin": Role.ADMIN, "admin_with_grant": Role.ADMIN, "super_admin": Role.SUPER_ADMIN}
    users = {
        name: make_user(
            db, hr, name=name.replace("_", " ").title(), role=roles.get(name, Role.EMPLOYEE)
        )
        for name in WORLD_ACTORS
    }
    for name in ("spoke", "spoke_with_grant"):
        make_spoke_assignment(db, users[name], it)
    make_spoke_assignment(db, users["other_spoke"], hr)
    normal = make_category(db, it, "Hardware")
    secret = make_category(db, it, "Investigations", is_confidential=True)
    for name in ("spoke_with_grant", "admin_with_grant", "employee_with_grant"):
        make_confidential_grant(db, users[name], secret)
    requester = users["requester"]
    tickets = {
        "normal": make_ticket(
            db,
            requester,
            it,
            status=TicketStatus.IN_PROGRESS,
            category=normal,
            assignee=users["assignee"],
            title="Laptop screen flickers",
        ),
        "secret": make_ticket(
            db,
            requester,
            it,
            status=TicketStatus.IN_PROGRESS,
            category=secret,
            assignee=users["assignee"],
            title="Sensitive matter",
        ),
        "hr": make_ticket(db, requester, hr, title="Payroll question"),
        "closed": make_ticket(db, requester, it, status=TicketStatus.CLOSED, category=normal),
    }
    for key in ("normal", "secret"):
        make_collaborator(db, tickets[key], users["collaborator"])
    return TicketWorld(it, hr, users, tickets, normal, secret)
