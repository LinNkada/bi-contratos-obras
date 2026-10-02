import pytest

from src.config import load_settings

REQUIRED = ["MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD"]


def test_load_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("MYSQL_DATABASE", "db_test")
    monkeypatch.setenv("MYSQL_USER", "user_test")
    monkeypatch.setenv("MYSQL_PASSWORD", "secret")
    monkeypatch.setenv("REFERENCE_DATE", "2026-09-30")

    settings = load_settings()

    assert settings.mysql_database == "db_test"
    assert settings.reference_date.isoformat() == "2026-09-30"


@pytest.mark.parametrize("missing", REQUIRED)
def test_load_settings_requires_variables(monkeypatch, missing):
    for name in REQUIRED:
        monkeypatch.setenv(name, "x")
    monkeypatch.delenv(missing)

    with pytest.raises(RuntimeError, match=missing):
        load_settings()