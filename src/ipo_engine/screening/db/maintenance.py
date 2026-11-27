"""
Maintenance operations that must step around the append-only protection of the audit tables.

Case data versions, review events and human-review events cannot be changed or deleted by normal
code (database triggers). Erasing a case on request is the one legitimate exception, so this module
lifts those triggers inside a single transaction and restores them before it commits. If anything
fails the transaction rolls back and the triggers are back, because the DDL is part of the
transaction on both SQLite and PostgreSQL. ``audit_events`` is never touched: it records that an
erasure happened, and holds identifiers only, never document contents or figures.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

ERASABLE = ("case_data_versions", "review_item_events", "human_review_events")


@contextmanager
def append_only_lifted(session: Session) -> Iterator[None]:
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        for table in ERASABLE:
            session.execute(_text(f"ALTER TABLE {table} DISABLE TRIGGER USER"))
        try:
            yield
        finally:
            for table in ERASABLE:
                session.execute(_text(f"ALTER TABLE {table} ENABLE TRIGGER USER"))
    elif dialect == "sqlite":
        _open_sqlite_transaction(session)
        for table in ERASABLE:
            for verb in ("update", "delete"):
                session.execute(_text(f"DROP TRIGGER IF EXISTS {table}_no_{verb}"))
        try:
            yield
        finally:
            for table in ERASABLE:
                for verb in ("UPDATE", "DELETE"):
                    session.execute(
                        _text(
                            f"CREATE TRIGGER IF NOT EXISTS {table}_no_{verb.lower()} "
                            f"BEFORE {verb} ON {table} "
                            f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;"
                        )
                    )
    else:  # pragma: no cover
        raise RuntimeError(f"unsupported database: {dialect}")


def _open_sqlite_transaction(session: Session) -> None:
    """Make sure the DDL below runs inside the transaction, so a rollback undoes it.

    pysqlite only issues BEGIN before an INSERT, UPDATE or DELETE. After a plain SELECT (or with
    nothing run yet) a DROP TRIGGER would commit on its own, and a failure later in the section
    would roll back only the re-create, leaving the append-only protection dropped for good.
    """
    raw = session.connection().connection.driver_connection
    if raw is not None and not raw.in_transaction:
        raw.execute("BEGIN")


def _text(sql: str):  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    return text(sql)
