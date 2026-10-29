from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MIN_PROD_JWT_SECRET_LENGTH = 32

MfaRole = Literal["super_admin", "admin", "spoke"]
CommaList = Annotated[list[str], NoDecode]
MfaRoleList = Annotated[list[MfaRole], NoDecode]


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


def _split_comma_list(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    env: Environment = Environment.DEV
    database_url: str = "postgresql+psycopg://ibotix:ibotix@localhost:5433/ibotix"
    test_database_url: str = "postgresql+psycopg://ibotix:ibotix@localhost:5433/ibotix_test"
    jwt_secret: SecretStr = SecretStr("dev-insecure-jwt-secret")
    access_token_minutes: int = Field(default=15, ge=1)
    refresh_token_days: int = Field(default=7, ge=1)
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cors_origins: CommaList = ["http://localhost:5173"]
    allowed_email_domains: CommaList = ["ibotix.ai"]
    frontend_base_url: str = "http://localhost:5173"
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = "helpdesk@ibotix.ai"
    smtp_starttls: bool = False
    attachment_dir: Path = Path("./var/attachments")
    max_upload_bytes: int = Field(default=10485760, ge=1)
    max_files_per_ticket: int = Field(default=5, ge=1)
    allowed_content_types: CommaList = [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "text/plain",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ]
    timezone: str = "Asia/Kolkata"
    worker_tick_seconds: int = Field(default=15, ge=1)
    sla_time_scale: float = Field(default=1.0, gt=0)
    mfa_required_roles: MfaRoleList = []
    field_encryption_key: SecretStr = SecretStr("")

    @field_validator(
        "cors_origins",
        "allowed_email_domains",
        "allowed_content_types",
        "mfa_required_roles",
        mode="before",
    )
    @classmethod
    def _parse_comma_list(cls, value: object) -> object:
        return _split_comma_list(value)

    @field_validator("cors_origins")
    @classmethod
    def _reject_wildcard_origin(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("CORS_ORIGINS must list explicit origins")
        return value

    @field_validator("allowed_email_domains")
    @classmethod
    def _normalize_domains(cls, value: list[str]) -> list[str]:
        return [domain.lower() for domain in value]

    @model_validator(mode="after")
    def _enforce_prod_rules(self) -> Self:
        if self.env is not Environment.PROD:
            return self
        if len(self.jwt_secret.get_secret_value()) < MIN_PROD_JWT_SECRET_LENGTH:
            raise ValueError("JWT_SECRET must be at least 32 characters in prod")
        if not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in prod")
        if self.sla_time_scale != 1.0:
            raise ValueError("SLA_TIME_SCALE must be exactly 1.0 in prod")
        if self.mfa_required_roles and not _is_fernet_key(self.field_encryption_key):
            raise ValueError("FIELD_ENCRYPTION_KEY must be a valid Fernet key when MFA is enabled")
        return self

    @property
    def mfa_enabled(self) -> bool:
        return bool(self.mfa_required_roles)


def _is_fernet_key(value: SecretStr) -> bool:
    try:
        Fernet(value.get_secret_value().encode())
    except ValueError:
        return False
    return True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
