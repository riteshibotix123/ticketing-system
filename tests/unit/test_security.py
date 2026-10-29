import base64
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import SecretStr

from app.core.config import Environment, Settings
from app.core.security import (
    InvalidAccessToken,
    create_access_token,
    decode_access_token,
    dummy_verify,
    hash_password,
    hash_token,
    new_opaque_token,
    password_policy_error,
    verify_password,
)

NOW = datetime(2026, 10, 27, 4, 30, tzinfo=UTC)


@pytest.fixture
def settings() -> Settings:
    return Settings(env=Environment.TEST)


def test_hash_and_verify_password() -> None:
    hashed = hash_password("Correct-Horse-9")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "Correct-Horse-9")
    assert not verify_password(hashed, "Wrong-Horse-9")
    assert not verify_password("not-a-hash", "Correct-Horse-9")


def test_dummy_verify_runs_without_error() -> None:
    dummy_verify("anything")


@pytest.mark.parametrize(
    ("password", "expected"),
    [
        ("Short1a", "Must be 12 to 128 characters"),
        ("A1" + "a" * 127, "Must be 12 to 128 characters"),
        ("ALLUPPERCASE123", "Must contain a lowercase letter"),
        ("alllowercase123", "Must contain an uppercase letter"),
        ("NoDigitsHereAtAll", "Must contain a digit"),
        ("ValidPassword1", None),
        ("A1" + "a" * 126, None),
    ],
)
def test_password_policy(password: str, expected: str | None) -> None:
    assert password_policy_error(password) == expected


def test_access_token_round_trip(settings: Settings) -> None:
    user_id = uuid.uuid4()
    issued = create_access_token(user_id, NOW, settings)
    assert issued.expires_in == 15 * 60
    assert decode_access_token(issued.token, NOW + timedelta(minutes=14), settings) == user_id


def test_access_token_has_no_role_claims(settings: Settings) -> None:
    issued = create_access_token(uuid.uuid4(), NOW, settings)
    claims = jwt.decode(issued.token, options={"verify_signature": False})
    assert set(claims) == {"sub", "iat", "exp", "jti"}


def test_expired_access_token_is_rejected(settings: Settings) -> None:
    issued = create_access_token(uuid.uuid4(), NOW, settings)
    with pytest.raises(InvalidAccessToken):
        decode_access_token(issued.token, NOW + timedelta(minutes=15), settings)


def test_tampered_access_token_is_rejected(settings: Settings) -> None:
    issued = create_access_token(uuid.uuid4(), NOW, settings)
    header, payload, signature = issued.token.split(".")
    tampered = f"{header}.{payload}.{signature[:-2]}{'AA' if signature[-2:] != 'AA' else 'BB'}"
    with pytest.raises(InvalidAccessToken):
        decode_access_token(tampered, NOW, settings)


def test_token_signed_with_other_secret_is_rejected(settings: Settings) -> None:
    other = Settings(env=Environment.TEST, jwt_secret=SecretStr("another-secret-entirely"))
    issued = create_access_token(uuid.uuid4(), NOW, other)
    with pytest.raises(InvalidAccessToken):
        decode_access_token(issued.token, NOW, settings)


def test_token_with_unsigned_algorithm_is_rejected(settings: Settings) -> None:
    issued = create_access_token(uuid.uuid4(), NOW, settings)
    payload = issued.token.split(".")[1]
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    with pytest.raises(InvalidAccessToken):
        decode_access_token(f"{header}.{payload}.", NOW, settings)


def test_token_missing_claims_is_rejected(settings: Settings) -> None:
    secret = settings.jwt_secret.get_secret_value()
    token = jwt.encode({"sub": str(uuid.uuid4())}, secret, algorithm="HS256")
    with pytest.raises(InvalidAccessToken):
        decode_access_token(token, NOW, settings)


def test_token_with_non_uuid_subject_is_rejected(settings: Settings) -> None:
    secret = settings.jwt_secret.get_secret_value()
    exp = int(NOW.timestamp()) + 60
    claims = {"sub": "someone", "iat": exp - 60, "exp": exp, "jti": "x"}
    token = jwt.encode(claims, secret, algorithm="HS256")
    with pytest.raises(InvalidAccessToken):
        decode_access_token(token, NOW, settings)


def test_opaque_tokens_are_random_and_hashed() -> None:
    first = new_opaque_token()
    second = new_opaque_token()
    assert first != second
    assert len(first) >= 43
    assert len(hash_token(first)) == 64
    assert hash_token(first) == hash_token(first)
    assert hash_token(first) != first
