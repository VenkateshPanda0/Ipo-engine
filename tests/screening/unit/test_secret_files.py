"""NAME_FILE support: secrets from files, and what wins when both are given."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ipo_engine.screening.core.config import SECRET_FILE_SETTINGS, Settings


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SECRET_FILE_SETTINGS:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(f"{name}_FILE", raising=False)


def test_a_secret_is_read_from_its_file_without_the_trailing_newline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    f = tmp_path / "sig"
    f.write_text("a-long-signing-key\n")
    monkeypatch.setenv("WEBHOOK_SIGNING_KEY_FILE", str(f))
    assert Settings().webhook_signing_key == "a-long-signing-key"


def test_every_listed_setting_can_come_from_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    for name in SECRET_FILE_SETTINGS:
        f = tmp_path / name
        f.write_text("sqlite:///x.db" if name == "DATABASE_URL" else f"value-of-{name}")
        monkeypatch.setenv(f"{name}_FILE", str(f))
    s = Settings()
    assert s.google_client_secret == "value-of-GOOGLE_CLIENT_SECRET"
    assert (
        s.smtp_password == "value-of-SMTP_PASSWORD"
        and s.s3_secret_access_key == "value-of-S3_SECRET_ACCESS_KEY"
    )
    assert s.api_keys == "value-of-API_KEYS" and s.database_url == "sqlite:///x.db"


def test_a_value_given_directly_wins_over_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    f = tmp_path / "k"
    f.write_text("from-file")
    monkeypatch.setenv("SMTP_PASSWORD_FILE", str(f))
    monkeypatch.setenv("SMTP_PASSWORD", "direct")
    assert Settings().smtp_password == "direct"


def test_an_unreadable_file_stops_the_start_with_a_clear_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET_FILE", str(tmp_path / "missing"))
    with pytest.raises((ValidationError, ValueError), match="GOOGLE_CLIENT_SECRET_FILE"):
        Settings()


def test_no_file_variables_means_no_change(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    assert Settings().webhook_signing_key is None
