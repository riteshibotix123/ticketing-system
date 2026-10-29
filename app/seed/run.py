from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.config import Environment, Settings
from app.core.enums import AccountState, SignupStatus, TicketStatus
from app.core.security import hash_password
from app.models.identity import SignupRequest, User
from app.models.org import Category, Department, SpokeAssignment
from app.models.ticket import Ticket
from app.policy import Actor
from app.schemas.tickets import CollaboratorBody, CommentBody, CreateTicketBody
from app.schemas.workflow import (
    AcknowledgeBody,
    AssignBody,
    ConfirmClosureBody,
    HoldBody,
    ReasonBody,
    ResolveBody,
    StatusBody,
    TransferBody,
)
from app.seed.data import (
    DEACTIVATION_REASON,
    DEPARTMENTS,
    GRANT_ISSUER,
    GRANTS,
    PEOPLE,
    SEED_PASSWORD,
    SIGNUPS,
    TICKETS,
    Acknowledge,
    AddCollaborator,
    AskRequester,
    Assign,
    Cancel,
    Comment,
    ConfirmClosure,
    Hold,
    PersonSeed,
    Reopen,
    Resolve,
    StartWork,
    TicketSeed,
    TicketStep,
    Transfer,
)
from app.services.audit import AuditService
from app.services.collaborators import CollaboratorService
from app.services.comments import CommentService
from app.services.confidential_grants import ConfidentialGrantService
from app.services.handlers import register_all
from app.services.me import MeService
from app.services.policy import PolicyService
from app.services.sla.levels import recompute_ticket
from app.services.sla.scanner import SlaScanner
from app.services.sla.timers import Timers
from app.services.tickets import TicketService
from app.services.workflow.closure import ClosureService
from app.services.workflow.progress import ProgressService
from app.services.workflow.transfer import TransferService

ORG_AGE: Final = timedelta(days=60)
SIGNUP_AGE: Final = timedelta(days=1)
DECISION_AGE: Final = timedelta(hours=12)


class SeedRefused(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SeedResult:
    created: bool
    users: int
    tickets: int


def seed(session: Session, settings: Settings, clock: Clock) -> SeedResult:
    if settings.env is Environment.PROD:
        raise SeedRefused("Seeding is not allowed when ENV=prod")
    marker = session.scalars(select(User.id).where(User.email == PEOPLE[0].email)).first()
    if marker is not None:
        return SeedResult(created=False, users=0, tickets=0)
    register_all()
    return Seeder(session, settings, clock.now()).run()


class Seeder:
    def __init__(self, session: Session, settings: Settings, now: datetime) -> None:
        self._session = session
        self._settings = settings
        self._now = now
        self._clock = FrozenClock(now - ORG_AGE)
        self._me = MeService(session)
        self._audit = AuditService(session, self._clock)
        self._users: dict[str, User] = {}
        self._categories: dict[tuple[str, str], Category] = {}
        self._password_hash = hash_password(SEED_PASSWORD)

    def run(self) -> SeedResult:
        departments = self._departments()
        created_users = self._people()
        self._contacts(departments)
        self._spokes()
        self._category_rows()
        self._grants()
        self._signups()
        self._deactivations()
        numbers = [self._ticket(ticket) for ticket in TICKETS]
        self._settle(numbers)
        return SeedResult(created=True, users=created_users, tickets=len(numbers))

    def _at(self, hours_ago: float) -> datetime:
        at = self._now - timedelta(hours=hours_ago)
        self._clock.set(at)
        return at

    def _actor(self, name: str) -> Actor:
        return self._me.actor_for(self._users[name])

    def _departments(self) -> dict[str, Department]:
        at = self._clock.now()
        departments: dict[str, Department] = {}
        for item in DEPARTMENTS:
            department = self._session.get(Department, item.code)
            if department is None:
                department = Department(
                    id=item.code, name=item.name, is_active=True, created_at=at, updated_at=at
                )
                self._session.add(department)
            departments[item.code] = department
        self._session.flush()
        return departments

    def _people(self) -> int:
        created = 0
        for person in PEOPLE:
            existing = self._session.scalars(select(User).where(User.email == person.email)).first()
            if existing is None:
                existing = self._new_user(person)
                created += 1
            self._users[person.name] = existing
        self._session.flush()
        return created

    def _new_user(self, person: PersonSeed) -> User:
        at = self._clock.now()
        approved = person.state in {AccountState.ACTIVE, AccountState.DEACTIVATED}
        verified = person.state is not AccountState.PENDING_VERIFICATION
        user = User(
            email=person.email,
            name=person.name,
            title=person.title,
            password_hash=self._password_hash,
            home_department_id=person.department,
            global_role=person.role,
            state=person.state,
            email_verified_at=at if verified else None,
            approved_at=at if approved else None,
            created_at=at,
            updated_at=at,
        )
        self._session.add(user)
        return user

    def _contacts(self, departments: dict[str, Department]) -> None:
        for item in DEPARTMENTS:
            if item.contact is not None:
                departments[item.code].escalation_contact_user_id = self._users[item.contact].id
        self._session.flush()

    def _spokes(self) -> None:
        issuer = self._users[GRANT_ISSUER]
        at = self._clock.now()
        for person in PEOPLE:
            for code in person.spoke_of:
                self._session.add(
                    SpokeAssignment(
                        user_id=self._users[person.name].id,
                        department_id=code,
                        granted_by_id=issuer.id,
                        granted_at=at,
                    )
                )
                self._audit.record(
                    action="spoke_mapping_added",
                    object_type="user",
                    object_id=self._users[person.name].id,
                    actor_id=issuer.id,
                    new_value={"department_id": code},
                    department_id=code,
                )
        self._session.flush()

    def _category_rows(self) -> None:
        at = self._clock.now()
        for item in DEPARTMENTS:
            for category_seed in item.categories:
                category = self._session.scalars(
                    select(Category).where(
                        Category.department_id == item.code, Category.name == category_seed.name
                    )
                ).first()
                if category is None:
                    category = Category(
                        department_id=item.code,
                        name=category_seed.name,
                        is_confidential=category_seed.confidential,
                        is_active=True,
                        created_at=at,
                        updated_at=at,
                    )
                    self._session.add(category)
                self._categories[(item.code, category_seed.name)] = category
        self._session.flush()

    def _grants(self) -> None:
        service = ConfidentialGrantService(self._session, self._clock)
        issuer = self._actor(GRANT_ISSUER)
        for grant in GRANTS:
            category = self._categories[(grant.department, grant.category)]
            service.create(issuer, str(self._users[grant.person].id), str(category.id))

    def _signups(self) -> None:
        decider = self._users[GRANT_ISSUER]
        created_at = self._now - SIGNUP_AGE
        decided_at = self._now - DECISION_AGE
        for item in SIGNUPS:
            user = self._users[item.person]
            rejected = item.rejection_reason is not None
            user.created_at = created_at
            user.updated_at = decided_at if rejected else created_at
            if user.email_verified_at is not None:
                user.email_verified_at = created_at
            request = SignupRequest(
                user_id=user.id,
                requested_role=item.requested_role,
                requested_department_id=user.home_department_id,
                status=SignupStatus.REJECTED if rejected else SignupStatus.PENDING,
                decided_by_id=decider.id if rejected else None,
                decision_reason=item.rejection_reason,
                decided_at=decided_at if rejected else None,
                created_at=created_at,
                updated_at=decided_at if rejected else created_at,
            )
            self._session.add(request)
            self._session.flush()
            if rejected:
                self._audit.record(
                    action="signup_rejected",
                    object_type="signup_request",
                    object_id=request.id,
                    actor_id=decider.id,
                    reason=item.rejection_reason,
                )
        self._session.flush()

    def _deactivations(self) -> None:
        actor = self._users[GRANT_ISSUER]
        for person in PEOPLE:
            if person.state is not AccountState.DEACTIVATED:
                continue
            user = self._users[person.name]
            user.deactivated_by_id = actor.id
            user.deactivated_at = self._clock.now()
            user.deactivation_reason = DEACTIVATION_REASON
            self._audit.record(
                action="user_deactivated",
                object_type="user",
                object_id=user.id,
                actor_id=actor.id,
                reason=DEACTIVATION_REASON,
            )
        self._session.flush()

    def _ticket(self, item: TicketSeed) -> str:
        self._at(item.hours_ago)
        category = self._categories[(item.department, item.category)]
        created = TicketService(self._session, self._clock, self._settings).create(
            self._actor(item.requester),
            CreateTicketBody(
                department_id=item.department,
                category_id=str(category.id),
                title=item.title,
                description=item.description,
                priority=item.priority,
                confidential=False,
            ),
        )
        for step in item.steps:
            self._apply(created.id, step)
        return created.id

    def _apply(self, number: str, step: TicketStep) -> None:
        self._at(step.hours_ago)
        actor = self._actor(step.by)
        progress = ProgressService(self._session, self._clock)
        closure = ClosureService(self._session, self._clock)
        match step:
            case Acknowledge():
                eta = self._now + timedelta(hours=step.eta_in_hours)
                progress.acknowledge(actor, number, AcknowledgeBody(eta=eta))
            case Assign():
                body = AssignBody(assignee_id=str(self._users[step.to].id))
                progress.assign(actor, number, body)
            case StartWork():
                progress.change_status(actor, number, StatusBody(status=TicketStatus.IN_PROGRESS))
            case AskRequester():
                body_ask = StatusBody(status=TicketStatus.AWAITING_REQUESTER, message=step.message)
                progress.change_status(actor, number, body_ask)
            case Hold():
                review = self._now + timedelta(hours=step.review_in_hours)
                progress.hold(actor, number, HoldBody(reason=step.reason, review_date=review))
            case Comment():
                comment = CommentBody(body=step.body, internal=step.internal)
                CommentService(self._session, self._clock).add(actor, number, comment)
            case AddCollaborator():
                collaborator = CollaboratorBody(user_id=str(self._users[step.person].id))
                CollaboratorService(self._session, self._clock).add(actor, number, collaborator)
            case Resolve():
                closure.resolve(actor, number, ResolveBody(summary=step.summary))
            case ConfirmClosure():
                feedback = ConfirmClosureBody(rating=step.rating, comment=step.comment)
                closure.confirm_closure(actor, number, feedback)
            case Reopen():
                closure.reopen(actor, number, ReasonBody(reason=step.reason))
            case Cancel():
                closure.cancel(actor, number, ReasonBody(reason=step.reason))
            case Transfer():
                category = self._categories[(step.department, step.category)]
                transfer = TransferBody(
                    department_id=step.department, category_id=str(category.id), reason=step.reason
                )
                TransferService(self._session, self._clock).transfer(actor, number, transfer)

    def _settle(self, numbers: list[str]) -> None:
        clock = FrozenClock(self._now)
        policy = PolicyService(self._session).current()
        scale = self._settings.sla_time_scale
        tickets = self._session.scalars(select(Ticket).where(Ticket.ticket_no.in_(numbers)))
        for ticket in tickets:
            Timers(self._session, ticket, policy, scale).reconcile(self._now)
            self._session.flush()
            recompute_ticket(self._session, clock, ticket)
        SlaScanner(self._session, clock, scale).run()
        self._session.flush()
