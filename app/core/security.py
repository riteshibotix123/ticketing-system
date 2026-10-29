import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
JWT_ALGORITHM = "HS256"
REFRESH_TOKEN_BYTES = 32
REQUIRED_CLAIMS = ("sub", "iat", "exp", "jti")

_LOWERCASE = re.compile(r"[a-z]")
_UPPERCASE = re.compile(r"[A-Z]")
_DIGIT = re.compile(r"[0-9]")

_hasher = PasswordHasher()


class InvalidAccessToken(Exception):
    pass


@dataclass(frozen=True, slots=True)
class IssuedAccessToken:
    token: str
    expires_in: int


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


@cache
def _dummy_hash() -> str:
    return _hasher.hash(secrets.token_urlsafe(16))


def dummy_verify(password: str) -> None:
    verify_password(_dummy_hash(), password)


def password_policy_error(password: str) -> str | None:
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        return f"Must be {PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters"
    if not _LOWERCASE.search(password):
        return "Must contain a lowercase letter"
    if not _UPPERCASE.search(password):
        return "Must contain an uppercase letter"
    if not _DIGIT.search(password):
        return "Must contain a digit"
    return None


def create_access_token(user_id: uuid.UUID, now: datetime, settings: Settings) -> IssuedAccessToken:
    lifetime = timedelta(minutes=settings.access_token_minutes)
    issued_at = int(now.timestamp())
    expires_in = int(lifetime.total_seconds())
    claims = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + expires_in,
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)
    return IssuedAccessToken(token=token, expires_in=expires_in)


def decode_access_token(token: str, now: datetime, settings: Settings) -> uuid.UUID:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={
                "require": list(REQUIRED_CLAIMS),
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
            },
        )
    except jwt.InvalidTokenError as exc:
        raise InvalidAccessToken from exc
    expires_at = claims.get("exp")
    subject = claims.get("sub")
    if not isinstance(expires_at, int) or not isinstance(subject, str):
        raise InvalidAccessToken
    if expires_at <= now.timestamp():
        raise InvalidAccessToken
    try:
        return uuid.UUID(subject)
    except ValueError as exc:
        raise InvalidAccessToken from exc


def new_opaque_token() -> str:
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
