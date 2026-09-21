from src.core.config import Settings


def test_settings_default_values() -> None:
    settings = Settings(_env_file=None)

    assert settings.max_failed_attempts == 5
    assert settings.lockout_minutes == 15
    assert settings.session_inactivity_minutes == 30


def test_settings_can_be_overridden_by_env(monkeypatch) -> None:
    monkeypatch.setenv("MAX_FAILED_ATTEMPTS", "3")
    monkeypatch.setenv("LOCKOUT_MINUTES", "10")
    monkeypatch.setenv("SESSION_INACTIVITY_MINUTES", "20")

    settings = Settings(_env_file=None)

    assert settings.max_failed_attempts == 3
    assert settings.lockout_minutes == 10
    assert settings.session_inactivity_minutes == 20
