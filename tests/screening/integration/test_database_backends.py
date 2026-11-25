"""The same guarantees on SQLite and PostgreSQL (set IPO_TEST_PG_ADMIN_URL for the latter)."""

from __future__ import annotations

from typing import Any

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ipo_engine.screening.db.base import Database, is_postgres, normalise_url
from ipo_engine.screening.db.migrate import alembic_config


@pytest.mark.parametrize(
    "given, expected",
    [
        ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgres://u@h:5432/db", "postgresql+psycopg://u@h:5432/db"),
        ("postgresql+psycopg://u@h/db", "postgresql+psycopg://u@h/db"),
        ("sqlite:///x.db", "sqlite:///x.db"),
    ],
)
def test_postgres_urls_are_normalised_to_the_psycopg_driver(given: str, expected: str) -> None:
    assert normalise_url(given) == expected
    assert is_postgres(given) == expected.startswith("postgresql")


def _db(app_factory: Any) -> Database:
    return app_factory(ACCOUNTS_ENABLED="true").app.state.container.db  # type: ignore[no-any-return]


def test_the_audit_table_is_append_only_on_every_backend(app_factory: Any) -> None:
    db = _db(app_factory)
    org = "org-default"
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit_events"
                " (ts, actor, action, entity_type, entity_id, details, org_id)"
                " VALUES (CURRENT_TIMESTAMP, 'a', 'x', 'y', 'z', '{}', :o)"
            ),
            {"o": org},
        )
    for sql in ("UPDATE audit_events SET actor = 'b'", "DELETE FROM audit_events"):
        with pytest.raises(DBAPIError, match="append-only"), db.engine.begin() as conn:
            conn.execute(text(sql))


def test_migrations_round_trip(app_factory: Any) -> None:
    db = _db(app_factory)
    cfg = alembic_config(db.engine)
    command.downgrade(cfg, "base")
    with pytest.raises(DBAPIError), db.engine.connect() as conn:
        conn.execute(text("SELECT count(*) FROM organisations"))  # the tables are gone
    command.upgrade(cfg, "head")
    with db.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM organisations")).scalar() == 1  # default org
