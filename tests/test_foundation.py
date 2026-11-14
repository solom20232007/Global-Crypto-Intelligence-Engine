from gcie.config import Settings
from gcie.health import health_status


def test_settings_use_safe_defaults(monkeypatch):
    monkeypatch.delenv("GCIE_ENV", raising=False)
    monkeypatch.delenv("GCIE_LOG_LEVEL", raising=False)
    settings = Settings.from_env()
    assert settings.environment == "development"
    assert settings.log_level == "INFO"


def test_settings_reject_unknown_environment(monkeypatch):
    monkeypatch.setenv("GCIE_ENV", "production-ish")
    try:
        Settings.from_env()
    except ValueError as exc:
        assert "GCIE_ENV" in str(exc)
    else:
        raise AssertionError("Invalid environment must be rejected")


def test_health_status_has_expected_contract():
    status = health_status()
    assert status["status"] == "ok"
    assert status["service"] == "global-crypto-intelligence-engine"
    assert status["version"]
    assert status["timestamp"].endswith("+00:00")
