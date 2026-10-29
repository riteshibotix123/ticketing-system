import re

DEPARTMENT_CODE_PATTERN = re.compile(r"^[A-Z]{2,6}$")
TICKET_PREFIX = "IBX"
MAX_TICKET_SEQUENCE = 999_999


def format_ticket_no(code: str, year: int, seq: int) -> str:
    if not DEPARTMENT_CODE_PATTERN.fullmatch(code):
        raise ValueError("department code must be 2 to 6 uppercase letters")
    if not 1000 <= year <= 9999:
        raise ValueError("year must have four digits")
    if not 1 <= seq <= MAX_TICKET_SEQUENCE:
        raise ValueError("sequence must be between 1 and 999999")
    return f"{TICKET_PREFIX}-{code}-{year}-{seq:06d}"
