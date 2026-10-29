from dataclasses import dataclass, field
from typing import Final

from app.core.enums import AccountState, Priority, Role

SEED_PASSWORD: Final = "Ibotix2026Demo"
EMAIL_DOMAIN: Final = "ibotix.ai"


def email_for(name: str) -> str:
    return f"{'.'.join(name.lower().split())}@{EMAIL_DOMAIN}"


@dataclass(frozen=True, slots=True)
class CategorySeed:
    name: str
    confidential: bool = False


@dataclass(frozen=True, slots=True)
class DepartmentSeed:
    code: str
    name: str
    categories: tuple[CategorySeed, ...]
    contact: str | None = None


@dataclass(frozen=True, slots=True)
class PersonSeed:
    name: str
    department: str
    title: str | None = None
    role: Role = Role.EMPLOYEE
    spoke_of: tuple[str, ...] = ()
    state: AccountState = AccountState.ACTIVE

    @property
    def email(self) -> str:
        return email_for(self.name)


@dataclass(frozen=True, slots=True)
class SignupSeed:
    person: str
    requested_role: Role
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class GrantSeed:
    person: str
    department: str
    category: str


@dataclass(frozen=True, slots=True)
class Acknowledge:
    by: str
    hours_ago: float
    eta_in_hours: float


@dataclass(frozen=True, slots=True)
class Assign:
    by: str
    to: str
    hours_ago: float


@dataclass(frozen=True, slots=True)
class StartWork:
    by: str
    hours_ago: float


@dataclass(frozen=True, slots=True)
class AskRequester:
    by: str
    hours_ago: float
    message: str


@dataclass(frozen=True, slots=True)
class Hold:
    by: str
    hours_ago: float
    reason: str
    review_in_hours: float


@dataclass(frozen=True, slots=True)
class Comment:
    by: str
    hours_ago: float
    body: str
    internal: bool = False


@dataclass(frozen=True, slots=True)
class AddCollaborator:
    by: str
    hours_ago: float
    person: str


@dataclass(frozen=True, slots=True)
class Resolve:
    by: str
    hours_ago: float
    summary: str


@dataclass(frozen=True, slots=True)
class ConfirmClosure:
    by: str
    hours_ago: float
    rating: int | None
    comment: str | None


@dataclass(frozen=True, slots=True)
class Reopen:
    by: str
    hours_ago: float
    reason: str


@dataclass(frozen=True, slots=True)
class Cancel:
    by: str
    hours_ago: float
    reason: str


@dataclass(frozen=True, slots=True)
class Transfer:
    by: str
    hours_ago: float
    department: str
    category: str
    reason: str


type TicketStep = (
    Acknowledge
    | Assign
    | StartWork
    | AskRequester
    | Hold
    | Comment
    | AddCollaborator
    | Resolve
    | ConfirmClosure
    | Reopen
    | Cancel
    | Transfer
)


@dataclass(frozen=True, slots=True)
class TicketSeed:
    requester: str
    department: str
    category: str
    title: str
    description: str
    priority: Priority
    hours_ago: float
    steps: tuple[TicketStep, ...] = field(default=())


DEPARTMENTS: Final = (
    DepartmentSeed(
        "IT",
        "IT & Infrastructure",
        (
            CategorySeed("Hardware"),
            CategorySeed("Software & Licences"),
            CategorySeed("Network & VPN"),
            CategorySeed("Access Request"),
        ),
        contact="Arjun Malhotra",
    ),
    DepartmentSeed(
        "ENG",
        "Engineering / Product",
        (CategorySeed("Build & CI"), CategorySeed("Dev Environment"), CategorySeed("Product Bug")),
        contact="Nikhil Bose",
    ),
    DepartmentSeed(
        "HR",
        "HR / People Operations",
        (
            CategorySeed("Employee Records", confidential=True),
            CategorySeed("Payroll"),
            CategorySeed("Leave & Attendance"),
            CategorySeed("Onboarding"),
        ),
        contact="Kavya Menon",
    ),
    DepartmentSeed(
        "ADM",
        "Administration & Facilities",
        (CategorySeed("Facilities"), CategorySeed("Travel & Transport")),
        contact="Suresh Pillai",
    ),
    DepartmentSeed(
        "FIN",
        "Finance & Accounts",
        (
            CategorySeed("Reimbursement"),
            CategorySeed("Invoices & Payments"),
            CategorySeed("Budget Request"),
        ),
        contact="Anil Desai",
    ),
    DepartmentSeed(
        "SEC",
        "Information Security / Compliance",
        (
            CategorySeed("Security Incident", confidential=True),
            CategorySeed("Phishing & Malware"),
            CategorySeed("Access Review"),
        ),
        contact="Pooja Reddy",
    ),
    DepartmentSeed(
        "SAL",
        "Sales / Business Development",
        (CategorySeed("CRM Access"), CategorySeed("Proposal Support")),
    ),
    DepartmentSeed(
        "OPS",
        "Project Delivery / Operations",
        (CategorySeed("Project Staffing"), CategorySeed("Delivery Escalation")),
        contact="Manish Agarwal",
    ),
    DepartmentSeed(
        "LEG",
        "Legal / Contracts",
        (
            CategorySeed("Contract Review", confidential=True),
            CategorySeed("NDA Request"),
            CategorySeed("Compliance Query"),
        ),
        contact="Deepa Krishnan",
    ),
)

PEOPLE: Final = (
    PersonSeed("Asha Verma", "ENG", "Software Engineer"),
    PersonSeed("Meera Iyer", "FIN", "Finance Analyst"),
    PersonSeed("Dev Patel", "IT", "IT Support Engineer"),
    PersonSeed("Rohan Mehta", "IT", "IT Lead", spoke_of=("IT", "ENG")),
    PersonSeed("Isha Gupta", "IT", "Senior IT Analyst", spoke_of=("IT",)),
    PersonSeed("Neha Kapoor", "HR", "HR Business Partner", spoke_of=("HR",)),
    PersonSeed("Sanjay Rao", "FIN", "Finance Manager", spoke_of=("FIN",)),
    PersonSeed("Tara Joshi", "ADM", "Facilities Manager"),
    PersonSeed("Vikram Singh", "SEC", "CISO", spoke_of=("SEC",)),
    PersonSeed("Aarav Khanna", "LEG", "Legal Counsel", spoke_of=("LEG",)),
    PersonSeed("Rahul Chopra", "SAL", "Sales Operations Lead", spoke_of=("SAL",)),
    PersonSeed("Sneha Bhatt", "OPS", "Delivery Manager", spoke_of=("OPS",)),
    PersonSeed("Priya Nair", "ADM", "Operations Admin", role=Role.ADMIN),
    PersonSeed("Karan Shah", "ADM", "CTO", role=Role.SUPER_ADMIN),
    PersonSeed("Mira Kulkarni", "ADM", "COO", role=Role.SUPER_ADMIN),
    PersonSeed("Arjun Malhotra", "IT", "Head of IT"),
    PersonSeed("Nikhil Bose", "ENG", "Head of Engineering"),
    PersonSeed("Kavya Menon", "HR", "Head of HR"),
    PersonSeed("Suresh Pillai", "ADM", "Head of Administration"),
    PersonSeed("Anil Desai", "FIN", "Head of Finance"),
    PersonSeed("Pooja Reddy", "SEC", "Head of Security"),
    PersonSeed("Manish Agarwal", "OPS", "Head of Delivery"),
    PersonSeed("Deepa Krishnan", "LEG", "Head of Legal"),
    PersonSeed("Kabir Sethi", "ENG", state=AccountState.PENDING_APPROVAL),
    PersonSeed("Ritu Bansal", "HR", state=AccountState.PENDING_APPROVAL),
    PersonSeed("Farhan Qureshi", "IT", state=AccountState.PENDING_APPROVAL),
    PersonSeed("Nitin Saxena", "SAL", state=AccountState.REJECTED),
    PersonSeed("Gaurav Thakur", "OPS", "Project Coordinator", state=AccountState.DEACTIVATED),
    PersonSeed("Leena Das", "FIN", state=AccountState.PENDING_VERIFICATION),
)

SIGNUPS: Final = (
    SignupSeed("Kabir Sethi", Role.EMPLOYEE),
    SignupSeed("Ritu Bansal", Role.ADMIN),
    SignupSeed("Farhan Qureshi", Role.SUPER_ADMIN),
    SignupSeed(
        "Nitin Saxena",
        Role.EMPLOYEE,
        rejection_reason="Please sign up with your Ibotix work account details",
    ),
    SignupSeed("Leena Das", Role.EMPLOYEE),
)

GRANT_ISSUER: Final = "Karan Shah"
GRANTS: Final = (
    GrantSeed("Neha Kapoor", "HR", "Employee Records"),
    GrantSeed("Vikram Singh", "SEC", "Security Incident"),
)

DEACTIVATION_REASON: Final = "Left the company at the end of the contract"

TICKETS: Final = (
    TicketSeed(
        "Asha Verma",
        "IT",
        "Software & Licences",
        "IDE licence renewal",
        "My IntelliJ licence expires on Friday. Please renew it for another year.",
        Priority.MEDIUM,
        2,
    ),
    TicketSeed(
        "Meera Iyer",
        "FIN",
        "Reimbursement",
        "Travel reimbursement for the Pune client visit",
        "Submitted the claim with receipts last week; it still shows as not received.",
        Priority.MEDIUM,
        20,
    ),
    TicketSeed(
        "Asha Verma",
        "ENG",
        "Build & CI",
        "Release pipeline fails on the signing step",
        "Every release build fails at code signing since the certificate rotation.",
        Priority.HIGH,
        30,
    ),
    TicketSeed(
        "Tara Joshi",
        "IT",
        "Network & VPN",
        "VPN disconnects every few minutes",
        "The VPN drops roughly every five minutes from the facilities office network.",
        Priority.MEDIUM,
        52,
    ),
    TicketSeed(
        "Meera Iyer",
        "IT",
        "Hardware",
        "Second monitor for the finance desk",
        "Requesting a second 24 inch monitor for month-end reconciliation work.",
        Priority.LOW,
        40,
        (Acknowledge("Isha Gupta", 38, 72),),
    ),
    TicketSeed(
        "Asha Verma",
        "IT",
        "Access Request",
        "Access to the production logs dashboard",
        "I need read access to the production logs dashboard for on-call duty.",
        Priority.MEDIUM,
        30,
        (
            Acknowledge("Rohan Mehta", 28, -1),
            StartWork("Rohan Mehta", 27),
            Comment("Rohan Mehta", 3, "Waiting on the security team to approve the role."),
        ),
    ),
    TicketSeed(
        "Meera Iyer",
        "FIN",
        "Invoices & Payments",
        "Vendor payment stuck in approval",
        "The payment to our cloud vendor has been pending approval for a week.",
        Priority.HIGH,
        26,
        (
            Acknowledge("Sanjay Rao", 25, 48),
            StartWork("Sanjay Rao", 24),
            AskRequester("Sanjay Rao", 5, "Please share the invoice number and the vendor name."),
        ),
    ),
    TicketSeed(
        "Asha Verma",
        "OPS",
        "Project Staffing",
        "Additional QA engineer for the Atlas project",
        "The Atlas project needs one more QA engineer for the next two sprints.",
        Priority.MEDIUM,
        30,
        (
            Acknowledge("Sneha Bhatt", 29, 120),
            StartWork("Sneha Bhatt", 28),
            Hold("Sneha Bhatt", 4, "Waiting for the vendor contract renewal", 72),
        ),
    ),
    TicketSeed(
        "Dev Patel",
        "HR",
        "Leave & Attendance",
        "Leave balance shows the wrong number of days",
        "My leave balance dropped by three days after the last attendance sync.",
        Priority.MEDIUM,
        30,
        (
            Acknowledge("Neha Kapoor", 28, 24),
            StartWork("Neha Kapoor", 27),
            Resolve(
                "Neha Kapoor",
                6,
                "Corrected the attendance sync and restored the three days of leave.",
            ),
        ),
    ),
    TicketSeed(
        "Asha Verma",
        "IT",
        "Software & Licences",
        "Install Docker Desktop",
        "Please install Docker Desktop on my laptop for local development.",
        Priority.LOW,
        120,
        (
            Acknowledge("Isha Gupta", 118, 48),
            StartWork("Isha Gupta", 100),
            Resolve("Isha Gupta", 72, "Installed Docker Desktop and assigned a licence seat."),
            ConfirmClosure("Asha Verma", 48, 5, "Quick and clear, thanks!"),
        ),
    ),
    TicketSeed(
        "Meera Iyer",
        "IT",
        "Hardware",
        "Laptop battery drains quickly",
        "My laptop battery lasts less than an hour even after a full charge.",
        Priority.MEDIUM,
        96,
        (
            Acknowledge("Rohan Mehta", 94, 48),
            StartWork("Rohan Mehta", 90),
            Resolve("Rohan Mehta", 48, "Recalibrated the battery and updated the firmware."),
            Reopen("Meera Iyer", 3, "The battery still drains within an hour."),
        ),
    ),
    TicketSeed(
        "Tara Joshi",
        "FIN",
        "Reimbursement",
        "Duplicate reimbursement request",
        "Raised a second reimbursement request for the same taxi receipts.",
        Priority.LOW,
        10,
        (Cancel("Tara Joshi", 9, "Raised by mistake, duplicate of an earlier request."),),
    ),
    TicketSeed(
        "Asha Verma",
        "HR",
        "Employee Records",
        "Update personal records after a name change",
        "I changed my surname and need my employee records and payslips updated.",
        Priority.MEDIUM,
        6,
        (Acknowledge("Neha Kapoor", 5, 48),),
    ),
    TicketSeed(
        "Dev Patel",
        "SEC",
        "Phishing & Malware",
        "Suspicious login prompts on the shared mailbox",
        "Several staff received fake login pages that look like our mail portal.",
        Priority.CRITICAL,
        3,
    ),
    TicketSeed(
        "Asha Verma",
        "IT",
        "Access Request",
        "Onboarding documents for a new joiner",
        "A new joiner in my team has not received the onboarding paperwork.",
        Priority.MEDIUM,
        10,
        (
            Acknowledge("Rohan Mehta", 9, 24),
            Transfer(
                "Rohan Mehta",
                8,
                "HR",
                "Onboarding",
                "Onboarding paperwork is handled by HR, not IT.",
            ),
        ),
    ),
    TicketSeed(
        "Meera Iyer",
        "IT",
        "Software & Licences",
        "Excel add-in crashes on startup",
        "The reporting add-in crashes Excel every time the workbook opens.",
        Priority.HIGH,
        8,
        (
            Acknowledge("Rohan Mehta", 7, 40),
            Assign("Rohan Mehta", "Dev Patel", 7),
            AddCollaborator("Rohan Mehta", 6, "Isha Gupta"),
            Comment("Dev Patel", 2, "Reproduced the crash; testing a clean add-in install.", True),
        ),
    ),
    TicketSeed(
        "Meera Iyer",
        "LEG",
        "Contract Review",
        "Review the renewal terms of the audit contract",
        "Please review the liability clauses in the audit firm's renewal contract.",
        Priority.MEDIUM,
        4,
    ),
)
