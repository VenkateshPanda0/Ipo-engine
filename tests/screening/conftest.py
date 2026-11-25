"""
Shared pytest fixtures.

The test session uses an isolated temporary data directory and SQLite database so
tests never touch ./data. ``app_factory`` builds fresh applications with custom
settings and inline (synchronous) document processing.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

_SESSION_DIR = Path(tempfile.mkdtemp(prefix="ipo-tests-"))
os.environ["DATA_DIR"] = str(_SESSION_DIR / "data")
os.environ["DATABASE_URL"] = f"sqlite:///{_SESSION_DIR / 'data' / 'test.db'}"
for _var in ("API_KEY", "API_KEYS", "REPORT_DATABASE_URL"):
    os.environ.pop(_var, None)

import pytest
from fastapi.testclient import TestClient

from ipo_engine.screening.core.config import Settings, get_settings
from ipo_engine.screening.models.company_data import CompanyData
from ipo_engine.screening.rules.registry import RuleRegistry
from tests.screening.fixtures.company_data_factory import CompanyDataFactory

get_settings.cache_clear()


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    shutil.rmtree(_SESSION_DIR, ignore_errors=True)


# Set IPO_TEST_PG_ADMIN_URL (for example postgresql://postgres@127.0.0.1:5432/postgres) to run every
# application-level test against PostgreSQL instead of SQLite: each app gets a fresh database.
PG_ADMIN_URL = os.environ.get("IPO_TEST_PG_ADMIN_URL")


def _new_postgres_database(created: list[str]) -> str:
    import uuid

    import psycopg

    name = f"t_{uuid.uuid4().hex[:16]}"
    assert PG_ADMIN_URL
    with psycopg.connect(PG_ADMIN_URL, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    created.append(name)
    head, _, _tail = PG_ADMIN_URL.rpartition("/")
    return f"{head}/{name}"


def _drop_postgres_databases(names: list[str]) -> None:
    if not names:
        return
    import psycopg

    assert PG_ADMIN_URL
    with psycopg.connect(PG_ADMIN_URL, autocommit=True) as conn:
        for name in names:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def company() -> CompanyData:
    """Default CompanyData with no failure under ruleset 2.0.0."""
    return CompanyDataFactory.create()


@pytest.fixture
def registry() -> RuleRegistry:
    """RuleRegistry bound to the current ruleset."""
    return RuleRegistry()


@pytest.fixture
def app_factory(tmp_path: Path) -> Iterator[Callable[..., TestClient]]:
    """Build an isolated app (own DB + data dir) with inline document processing."""
    from ipo_engine.screening.main import create_app

    clients: list[TestClient] = []
    pg_databases: list[str] = []

    def make(**overrides: Any) -> TestClient:
        env = {
            "DATA_DIR": str(tmp_path / "data"),
            "DATABASE_URL": f"sqlite:///{tmp_path / 'app.db'}",
        }
        if PG_ADMIN_URL and "DATABASE_URL" not in overrides:
            env["DATABASE_URL"] = _new_postgres_database(pg_databases)
        env.update({k: str(v) for k, v in overrides.items()})
        settings = Settings(**env)  # type: ignore[arg-type]
        client = TestClient(create_app(settings, inline_processing=True))
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)
    _drop_postgres_databases(pg_databases)
