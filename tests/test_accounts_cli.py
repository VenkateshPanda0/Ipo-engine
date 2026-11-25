"""The `ipo accounts` commands: first-admin bootstrap and recovery without a running server."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from ipo_engine.cli import main
from ipo_engine.screening.core.config import get_settings


@pytest.fixture(autouse=True)
def _db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _org_id(out: str) -> str:
    return out.split()[1]


def test_bootstrap_an_admin_and_use_the_token(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["accounts", "create-org", "Acme Capital"]) == 0
    org = _org_id(capsys.readouterr().out)
    assert main(["accounts", "add-member", org, "Ann@Acme.example", "--role", "admin"]) == 0
    capsys.readouterr()
    assert main(["accounts", "create-token", org, "ann@acme.example", "--name", "first"]) == 0
    out = capsys.readouterr()
    token = out.out.strip()
    assert token.startswith("ipo_") and "stored" in out.err

    from ipo_engine.screening.db.base import Database
    from ipo_engine.screening.services.accounts import AccountService

    acc = AccountService(Database(get_settings().database_url))
    principal = acc.authenticate_token(token)
    assert principal is not None and principal.org_id == org and principal.role.value == "admin"

    assert main(["accounts", "suspend", "ann@acme.example"]) == 0
    assert acc.authenticate_token(token) is None
    assert main(["accounts", "reinstate", "ann@acme.example"]) == 0
    assert acc.authenticate_token(token) is not None


def test_errors_are_reported_not_raised(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["accounts", "add-member", "no-such-org", "x@y.example"]) == 1
    assert "error:" in capsys.readouterr().err
    assert main(["accounts", "create-org", "   "]) == 1
