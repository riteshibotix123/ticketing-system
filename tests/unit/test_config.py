from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Environment, Settings, get_settings

STRONG_SECRET = SecretStr("x" * 32)


def test_defaults() -> None:
    settings = Settings()
    assert settings.env is Environment.DEV
    assert settings.access_token_minutes == 15
    assert settings.refresh_token_days == 7
    assert settings.allowed_email_domains == ["ibotix.ai"]
    assert settings.max_upload_bytes == 10485760
    assert settings.max_files_per_ticket == 5
    assert settings.timezone == "Asia/Kolkata"
    assert settings.worker_tick_seconds == 15
    assert settings.sla_time_scale == 1.0
    assert settings.mfa_required_roles == []
    assert settings.mfa_enabled is False
    assert settings.cookie_secure is False


def test_comma_lists_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "Ibotix.AI,partner.ai")
    monkeypatch.setenv("MFA_REQUIRED_ROLES", "super_admin,admin")
    settings = Settings()
    assert settings.cors_origins == ["http://a.test", "http://b.test"]
    assert settings.allowed_email_domains == ["ibotix.ai", "partner.ai"]
    assert settings.mfa_required_roles == ["super_admin", "admin"]
    assert settings.mfa_enabled is True


def test_empty_mfa_roles_disable_mfa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MFA_REQUIRED_ROLES", "")
    assert Settings().mfa_enabled is False


def test_unknown_mfa_role_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MFA_REQUIRED_ROLES", "employee")
    with pytest.raises(ValidationError):
        Settings()


def test_wildcard_cors_origin_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ValidationError):
        Settings()


def test_env_file_is_read(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("ACCESS_TOKEN_MINUTES=30\n", encoding="utf-8")
    assert Settings().access_token_minutes == 30


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_valid_prod_settings() -> None:
    settings = Settings(
        env=Environment.PROD, jwt_secret=STRONG_SECRET, cookie_secure=True, sla_time_scale=1.0
    )
    assert settings.env is Environment.PROD


def test_prod_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(env=Environment.PROD, jwt_secret=SecretStr("short"), cookie_secure=True)


def test_prod_rejects_insecure_cookie() -> None:
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(env=Environment.PROD, jwt_secret=STRONG_SECRET, cookie_secure=False)


def test_prod_rejects_scaled_sla_time() -> None:
    with pytest.raises(ValidationError, match="SLA_TIME_SCALE"):
        Settings(
            env=Environment.PROD,
            jwt_secret=STRONG_SECRET,
            cookie_secure=True,
            sla_time_scale=0.0166667,
        )


def test_non_prod_allows_scaled_sla_time() -> None:
    assert Settings(env=Environment.TEST, sla_time_scale=0.0166667).sla_time_scale == 0.0166667
